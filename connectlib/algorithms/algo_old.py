import substratools
import pickle

import numpy as np

from abc import abstractmethod
from pathlib import Path
from typing import Dict, Tuple, Any, Optional


class Algo(substratools.CompositeAlgo):
    SEED: int

    def preprocessing(self, x: Any, y: Optional[Any] = None) -> Tuple[Any, Any]:
        if y is not None:
            return x, y
        else:
            return x

    @abstractmethod
    def perform_update(self, x: Any, y: Any):
        raise NotImplementedError

    @abstractmethod
    def test(self, x: Any):
        raise NotImplementedError

    @property
    @abstractmethod
    def weights(self) -> Dict[str, np.array]:
        raise NotImplementedError

    @weights.setter
    @abstractmethod
    def weights(self, weights: Dict[str, np.array]):
        raise NotImplementedError

    @abstractmethod
    def load(self, path: Path):
        raise NotImplementedError

    @abstractmethod
    def save(self, path: Path):
        raise NotImplementedError

    # Substra methods
    def train(
        self,
        X: Any,
        y: Any,
        head_model: Optional["Algo"],  # instance of own type
        trunk_model: Optional[Dict[str, np.array]],  # shared state
        rank: int,
    ) -> Tuple["Algo", Dict[str, np.array]]:

        if head_model is None:
            head_model = self

        if trunk_model is None:
            print("trunk model is None")
            # raise TypeError("you need to run InitAggregator first")
        else:
            head_model.weights = trunk_model

        X, y = self.preprocessing(X, y)
        head_model.perform_update(X, y)

        return head_model, head_model.weights

    def predict(
        self, X: Any, head_model: Optional["Algo"], trunk_model: Optional[Dict[str, np.array]]
    ):
        assert head_model is not None
        assert trunk_model is not None

        head_model.weights = trunk_model

        X = self.preprocessing(X)
        return head_model.test(X)

    def load_trunk_model(self, path: str) -> Dict[str, np.array]:
        with Path(path).open("rb") as f:
            weights = pickle.load(f)
        return weights

    def save_trunk_model(self, model: Dict[str, np.array], path: str):
        with Path(path).open("wb") as f:
            pickle.dump(model, f)

    def load_head_model(self, path: str) -> "Algo":
        self.load(Path(path))
        return self

    def save_head_model(self, model: "Algo", path: str):
        model.save(Path(path))
