import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import torch

from connectlib import execute_experiment
from connectlib.algorithms.pytorch import TorchScaffoldAlgo
from connectlib.algorithms.pytorch.weight_manager import increment_parameters
from connectlib.dependency import Dependency
from connectlib.evaluation_strategy import EvaluationStrategy
from connectlib.exceptions import NumUpdatesValueError
from connectlib.index_generator import NpIndexGenerator
from connectlib.schemas import ScaffoldAveragedStates
from connectlib.schemas import ScaffoldSharedState
from connectlib.strategies import Scaffold
from tests import utils
from tests.algorithms.pytorch.torch_tests_utils import assert_model_parameters_equal
from tests.algorithms.pytorch.torch_tests_utils import assert_tensor_list_equal
from tests.algorithms.pytorch.torch_tests_utils import assert_tensor_list_not_zeros

logger = logging.getLogger(__name__)
current_folder = Path(__file__).parent


@pytest.mark.substra
@pytest.mark.slow
def test_pytorch_scaffold_algo_weights(
    network,
    torch_linear_model,
    train_linear_nodes,
    aggregation_node,
    session_dir,
):
    """Check the weight initialisation, aggregation and set weights.
    The aggregation itself is tested at the strategy level, here we test
    the pytorch layer.
    """
    num_updates = 2
    num_rounds = 2
    batch_size = 1

    seed = 42
    torch.manual_seed(seed)
    perceptron = torch_linear_model()
    nig = NpIndexGenerator(
        batch_size=batch_size,
        num_updates=num_updates,
        shuffle=True,
        drop_last=False,
    )

    class MyAlgo(TorchScaffoldAlgo):
        def __init__(self):
            super().__init__(
                model=perceptron,
                criterion=torch.nn.MSELoss(),
                optimizer=torch.optim.SGD(perceptron.parameters(), lr=0.1),
                index_generator=nig,
            )

        def _local_train(self, x: Any, y: Any):
            super()._local_train(torch.from_numpy(x).float(), torch.from_numpy(y).float())

        def _local_predict(self, x: Any) -> Any:
            y_pred = super()._local_predict(torch.from_numpy(x).float())
            return y_pred.detach().numpy()

    my_algo = MyAlgo()
    algo_deps = Dependency(
        pypi_dependencies=["torch", "numpy"],
        editable_mode=True,
    )
    strategy = Scaffold(aggregation_lr=1)
    my_eval_strategy = None

    compute_plan = execute_experiment(
        client=network.clients[0],
        algo=my_algo,
        strategy=strategy,
        train_data_nodes=train_linear_nodes,
        evaluation_strategy=my_eval_strategy,
        aggregation_node=aggregation_node,
        num_rounds=num_rounds,
        dependencies=algo_deps,
        experiment_folder=session_dir / "experiment_folder",
        clean_models=False,
    )

    # Wait for the compute plan to be finished
    utils.wait(network.clients[0], compute_plan)

    rank_0_local_models = utils.download_composite_models_by_rank(network, session_dir, my_algo, compute_plan, rank=0)
    rank_2_local_models = utils.download_composite_models_by_rank(network, session_dir, my_algo, compute_plan, rank=2)

    # Download the aggregate output
    aggregate_task = network.clients[0].list_aggregatetuple(
        filters=[f"aggregatetuple:compute_plan_key:{compute_plan.key}", f"aggregatetuple:rank:{1}"]
    )[0]
    model_key = aggregate_task.aggregate.models[0].key
    network.clients[0].download_model(model_key, session_dir)
    model_path = session_dir / f"model_{model_key}"
    aggregate_model = pickle.loads(model_path.read_bytes())

    # Assert the model initialisation is the same for every model
    assert_model_parameters_equal(rank_0_local_models[0].model, rank_0_local_models[1].model)
    assert_tensor_list_equal(
        rank_0_local_models[0]._client_control_variate, rank_0_local_models[1]._client_control_variate
    )

    # assert the _client_control_variate have been updated
    assert_tensor_list_not_zeros(rank_0_local_models[0]._client_control_variate)
    assert_tensor_list_not_zeros(rank_0_local_models[1]._client_control_variate)

    # Assert that the weights are well set
    for model_0, model_2 in zip(rank_0_local_models, rank_2_local_models):
        increment_parameters(model_0.model, aggregate_model.avg_parameters_update, with_batch_norm_parameters=True)
        assert_model_parameters_equal(model_0.model, model_2.model)

    # The local models and _client_control_variate are always the same on every node, as both nodes have the same data
    assert_model_parameters_equal(rank_2_local_models[0].model, rank_2_local_models[1].model)
    assert_tensor_list_equal(
        rank_2_local_models[0]._client_control_variate, rank_2_local_models[1]._client_control_variate
    )


@pytest.mark.substra
@pytest.mark.slow
def test_pytorch_scaffold_algo_performance(
    network,
    torch_linear_model,
    train_linear_nodes,
    test_linear_nodes,
    aggregation_node,
    session_dir,
    rtol,
):
    """End to end test for torch fed avg algorithm."""
    num_updates = 100
    num_rounds = 3
    expected_performance = 0.0127768706

    seed = 42
    torch.manual_seed(seed)
    perceptron = torch_linear_model()
    nig = NpIndexGenerator(
        batch_size=32,
        num_updates=num_updates,
        shuffle=True,
        drop_last=False,
    )

    class MyAlgo(TorchScaffoldAlgo):
        def __init__(
            self,
        ):
            super().__init__(
                optimizer=torch.optim.SGD(perceptron.parameters(), lr=0.1),
                criterion=torch.nn.MSELoss(),
                model=perceptron,
                index_generator=nig,
            )

        def _local_train(self, x: Any, y: Any):
            super()._local_train(torch.from_numpy(x).float(), torch.from_numpy(y).float())

        def _local_predict(self, x: Any) -> Any:
            y_pred = super()._local_predict(torch.from_numpy(x).float())
            return y_pred.detach().numpy()

    my_algo = MyAlgo()
    algo_deps = Dependency(
        pypi_dependencies=["torch", "numpy"],
        editable_mode=True,
    )

    strategy = Scaffold(aggregation_lr=1)
    my_eval_strategy = EvaluationStrategy(
        test_data_nodes=test_linear_nodes, rounds=[num_rounds]  # test only at the last round
    )

    compute_plan = execute_experiment(
        client=network.clients[0],
        algo=my_algo,
        strategy=strategy,
        train_data_nodes=train_linear_nodes,
        evaluation_strategy=my_eval_strategy,
        aggregation_node=aggregation_node,
        num_rounds=num_rounds,
        dependencies=algo_deps,
        experiment_folder=session_dir / "experiment_folder",
    )

    # Wait for the compute plan to be finished
    utils.wait(network.clients[0], compute_plan)

    testtuples = network.clients[0].list_testtuple(filters=[f"testtuple:compute_plan_key:{compute_plan.key}"])
    testtuple = testtuples[0]
    assert list(testtuple.test.perfs.values())[0] == pytest.approx(expected_performance, rel=rtol)


def test_train_skip(rtol):
    # check the results of the train function with simple data and model
    torch.manual_seed(42)
    n_samples = 32

    class Perceptron(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear1 = torch.nn.Linear(1, 1, bias=False)
            # we init the weights at 0
            self.linear1.weight.data.fill_(0)

        def forward(self, x):
            out = self.linear1(x)
            return out

    dummy_model = Perceptron()
    nig = NpIndexGenerator(
        batch_size=n_samples,
        num_updates=2,
        shuffle=True,
        drop_last=False,
    )

    class MyAlgo(TorchScaffoldAlgo):
        def __init__(
            self,
        ):
            super().__init__(
                optimizer=torch.optim.SGD(dummy_model.parameters(), lr=0.5),
                criterion=torch.nn.MSELoss(),
                model=dummy_model,
                index_generator=nig,
            )

        def _local_train(self, x: Any, y: Any):
            super()._local_train(torch.from_numpy(x).float(), torch.from_numpy(y).float())

        def _local_predict(self, x: Any) -> Any:
            y_pred = super()._local_predict(torch.from_numpy(x).float())
            return y_pred.detach().numpy()

    my_algo = MyAlgo()

    # we generate linear data x=ay+b with a = 2, b = 0
    a = 2
    x = np.ones((n_samples, 1))  # ones
    y = np.ones((n_samples, 1)) * a  # twos
    shared_states: ScaffoldSharedState = my_algo.train(x=x, y=y, shared_state=None, _skip=True)

    # the model should overfit so that weight_updates (= the new weighs) = a in x=ay+b
    assert np.allclose(a, shared_states.parameters_update, rtol=rtol)
    # lr * num_updates = 1 so control_variate_update = - parameters_update
    assert np.allclose(-1 * a, shared_states.control_variate_update, rtol=rtol)
    assert np.allclose(n_samples, shared_states.n_samples, rtol)
    # server_control_variate is init to zero should not be modified
    assert np.allclose(np.array([[0.0]]), shared_states.server_control_variate, rtol)

    # we create a ScaffoldAveragedStates with the ouput state of the train fct and predict on x
    avg_shared_states = ScaffoldAveragedStates(
        server_control_variate=shared_states.control_variate_update,
        avg_parameters_update=shared_states.parameters_update,
    )
    predictions = my_algo.predict(x=x, shared_state=avg_shared_states, _skip=True)

    # the model should overfit so that predictions = y
    assert np.allclose(y, predictions, rtol=rtol)


def test_update_current_lr(rtol):
    # test the update_current_lr() fct with optimizer only and optimizer+scheduler
    torch.manual_seed(42)
    initial_lr = 0.5

    class DummyModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.linear1 = torch.nn.Linear(1, 1, bias=False)

        def forward(self, x):
            out = self.linear1(x)
            return out

    dummy_model = DummyModel()

    optimizer = torch.optim.SGD(dummy_model.parameters(), lr=initial_lr)
    nig = NpIndexGenerator(
        batch_size=1,
        num_updates=1,
    )

    class MyAlgo(TorchScaffoldAlgo):
        def __init__(
            self,
        ):
            super().__init__(
                optimizer=optimizer,
                criterion=torch.nn.MSELoss(),
                model=dummy_model,
                index_generator=nig,
            )

        def _local_train(self, x: Any, y: Any):
            super()._local_train(torch.from_numpy(x).float(), torch.from_numpy(y).float())

        def _local_predict(self, x: Any) -> Any:
            y_pred = super()._local_predict(torch.from_numpy(x).float())
            return y_pred.detach().numpy()

    my_algo = MyAlgo()
    my_algo._update_current_lr()
    assert pytest.approx(my_algo._current_lr, rel=rtol) == initial_lr

    # test with scheduler
    # this scheduler multiplies the lr by 0.1 at each _scheduler.step()
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.1)
    nig = NpIndexGenerator(
        batch_size=1,
        num_updates=2,
    )

    class MyAlgo(TorchScaffoldAlgo):
        def __init__(
            self,
        ):
            super().__init__(
                optimizer=optimizer,
                scheduler=scheduler,
                criterion=torch.nn.MSELoss(),
                model=dummy_model,
                index_generator=nig,
            )

        def _local_train(self, x: Any, y: Any):
            super()._local_train(torch.from_numpy(x).float(), torch.from_numpy(y).float())

        def _local_predict(self, x: Any) -> Any:
            y_pred = super()._local_predict(torch.from_numpy(x).float())
            return y_pred.detach().numpy()

    my_algo = MyAlgo()
    # init : the lr is initial_lr
    my_algo._update_current_lr()
    assert pytest.approx(my_algo._current_lr, rel=rtol) == initial_lr
    # after one _scheduler.step(), lr should be initial_lr * 0.1
    my_algo._scheduler.step()
    my_algo._update_current_lr()
    assert pytest.approx(my_algo._current_lr, rel=rtol) == initial_lr * 0.1


@pytest.mark.parametrize("num_updates", [-10, 0])
def test_pytorch_num_updates_error(num_updates):
    """Check that num_updates <= 0 raise a ValueError."""
    nig = NpIndexGenerator(
        batch_size=32,
        num_updates=num_updates,
    )

    class MyAlgo(TorchScaffoldAlgo):
        def __init__(
            self,
        ):
            super().__init__(
                optimizer=None,
                criterion=None,
                model=None,
                index_generator=nig,
            )

        def _local_train(self, x: Any, y: Any):
            super()._local_train(torch.from_numpy(x).float(), torch.from_numpy(y).float())

        def _local_predict(self, x: Any) -> Any:
            y_pred = super()._local_predict(torch.from_numpy(x).float())
            return y_pred.detach().numpy()

    with pytest.raises(NumUpdatesValueError):
        MyAlgo()