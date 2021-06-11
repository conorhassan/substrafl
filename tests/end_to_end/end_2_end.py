import substra

import numpy as np
import os

from pathlib import Path
from loguru import logger
import zipfile

from connectlib.algorithms import Algo
from connectlib.remote import remote_data
from connectlib.orchestrator import Orchestrator
from connectlib.strategies import FedAVG
from connectlib.nodes import AggregationNode, TestDataNode, TrainDataNode

ASSETS_DIR = Path(__file__).parent / "test_assets"
DEFAULT_PERMISSIONS = substra.sdk.schemas.Permissions(public=True, authorized_ids=list())


def register_dataset(client: substra.Client, asset_dir: Path):
    # Add the dataset
    # This is the data opener that for nows returns directly a mdf
    logger.info("Adding dataset")
    dataset_key = client.add_dataset(
        substra.sdk.schemas.DatasetSpec(
            name="opener - MDF",
            data_opener=asset_dir / "opener" / "opener.py",
            type="opener - MDF",
            description=asset_dir / "opener" / "description.md",
            permissions=DEFAULT_PERMISSIONS,
        )
    )

    # Add the data samples : one data sample with the MDF inside
    logger.info("Adding data sample")
    data_sample_key = client.add_data_sample(
        substra.sdk.schemas.DataSampleSpec(
            path=asset_dir / "datasample",
            test_only=False,
            data_manager_keys=[dataset_key],
        )
    )

    return dataset_key, data_sample_key


def make_objective(client: substra.Client, asset_dir: Path):
    # objective_key is a key to the metric your registered
    # objective = asset_factory.create_objective(dataset=org1_client.get_dataset(org1_dataset_key))
    # data['test_data_sample_keys'] = load_data_samples_keys(data_samples)
    zip_objective(asset_dir=asset_dir)

    objective = {
        "name": "avg strategy end-to-end",
        "description": ASSETS_DIR / "opener" / "description.md",
        "metrics_name": "accuracy",
        "metrics": ASSETS_DIR / "objective" / "metrics.zip",
        "permissions": DEFAULT_PERMISSIONS,  # {"public": False, "authorized_ids": []},
    }

    return objective


def zip_objective(asset_dir: Path):
    # Create necessary archive to register the operation on substra
    # the previous metric.zip will be overwritten
    operation_dir = ASSETS_DIR / "objective"
    archive_path = operation_dir / "metrics.zip"
    with zipfile.ZipFile(archive_path, "w") as z:
        for filepath in operation_dir.glob("*[!.zip]"):
            print(f"zipped in {filepath}")
            z.write(filepath, arcname=os.path.basename(filepath))


class MyAlgo(Algo):
    def delayed_init(self, seed: int, *args, **kwargs):
        self._shared_state = {"test": np.random.randn(8, 16)}

    @remote_data
    def train(self, x: np.array, y: np.array, num_updates: int, shared_state):
        return self._shared_state

    @remote_data
    def predict(self, x: np.array, shared_state):
        # return np.random.randint(0, 2, size=(len(x), 1))
        return shared_state

    def load(self, path: Path):
        pass

    def save(self, path: Path):
        assert path.parent.exists()
        with path.open("w") as f:
            f.write("test")


org1_client = substra.Client(debug=True)
org2_client = substra.Client(debug=True)

org1_dataset_key, org1_data_sample_key = register_dataset(org1_client, ASSETS_DIR)
org2_dataset_key, org2_data_sample_key = register_dataset(org2_client, ASSETS_DIR)
# TODO: check client.add_test_datasamples (ask Thais or Fabien)

# TODO: how to have multiple organizations in a debug workflow (ask Fabien)
train_data_nodes = [
    TrainDataNode("0", org1_dataset_key, [org1_data_sample_key]),
    TrainDataNode("1", org1_dataset_key, [org1_data_sample_key]),
]

OBJECTIVE = make_objective(org1_client, ASSETS_DIR)
org1_objective_key = org1_client.add_objective(
    {
        "name": OBJECTIVE["name"],
        "description": str(OBJECTIVE["description"]),
        "metrics_name": OBJECTIVE["metrics_name"],
        "metrics": str(OBJECTIVE["metrics"]),
        "test_data_sample_keys": [org1_data_sample_key],
        "test_data_manager_key": org1_dataset_key,
        "permissions": OBJECTIVE["permissions"],
    },
)

test_data_nodes = [
    TestDataNode(
        "0", org1_dataset_key, [org1_data_sample_key], objective_key=org1_objective_key
    ),
    TestDataNode(
        "0", org1_dataset_key, [org1_data_sample_key], objective_key=org1_objective_key
    ),
]

aggregation_node = AggregationNode("0")

my_algo = MyAlgo()
strategy = FedAVG(num_updates=1)

orchestrator = Orchestrator(my_algo, strategy, num_rounds=1)
orchestrator.run(
    org1_client, train_data_nodes, aggregation_node, test_data_nodes=test_data_nodes
)

# TODO: to test fed-avg set weights to constant values and