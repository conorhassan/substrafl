import abc
import logging
from typing import Any
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class BaseIndexGenerator(abc.ABC):
    """Base class for the index generator, must be
    subclassed.
    """

    def __init__(
        self,
        n_samples: int,
        batch_size: Optional[int],
        num_updates: int,
        shuffle: bool = True,
        drop_last: bool = True,
        seed: int = 42,
    ):
        """Init method

        Args:
            n_samples (int): The number of samples in one epoch, i.e. the number of indexes you want to
                draw your batches from.
            batch_size (Optional[int]): The size of each batch. If set to None, the batch_size will be
                the number of samples.

        Raises:
            ValueError: if n_samples is negative
            ValueError: if batch_size is negative
        """
        # Validates n_samples
        if n_samples < 0:
            raise ValueError(f"n_samples must be non negative but {n_samples} was passed.")

        self._n_samples: int = n_samples

        # Validates batch_size
        if batch_size is None:
            logger.info("None was passed as a batch size. It will be set to n_sample size.")
            self._batch_size: int = self._n_samples

        elif batch_size < 0:
            raise ValueError(f"batch_size must be non negative but {batch_size} was passed.")

        elif batch_size > n_samples:
            logger.info(
                (
                    "The batch size ({batch_size}) is greater than the number of samples: n_samples."
                    "This is not allowed. Batch_size is now updated to equal number of samples ({n_samples})"
                ).format(batch_size=batch_size, n_samples=n_samples)
            )
            self._batch_size = self._n_samples

        else:
            self._batch_size = batch_size

        self._rng = np.random.default_rng(seed)
        self._shuffle: bool = shuffle
        self._drop_last: bool = drop_last
        self._num_updates: int = num_updates
        self._counter: int = 0
        self._n_epoch_generated: int = 0

    @property
    def counter(self) -> int:
        """Number of calls made to the iterator

        Returns:
            int: Number of calls made to the iterator
        """
        return self._counter

    @property
    def n_epoch_generated(self) -> int:
        """Number of epochs generated

        Returns:
            int: number of epochs generated
        """
        return self._n_epoch_generated

    def __iter__(self) -> "BaseIndexGenerator":
        """Required methods for generators."""
        return self

    @abc.abstractclassmethod
    def __next__(self) -> Any:
        """Shall return a python object (batch_index) which
        is used for selecting each batch in the training loop method during training in this way :
        `x[batch_index], y[batch_index]`

        Shall also update self._counter and self._n_epoch_generated

        After self._num_updates call, raise StopIteration.

        Returns:
            Any: The batch indexes.
        """
        raise NotImplementedError

    def reset_counter(self):
        """Reset the counter to
        prepare for the next generation
        of batches.
        """
        self._counter = 0