# Copyright (c) Facebook, Inc. and its affiliates.
import random

from torchdata.datapipes import functional_datapipe
from torchdata.datapipes.iter import IterDataPipe
from torch.utils.data import DataChunk
from typing import Callable, Iterator, Optional, Sized, TypeVar

T_co = TypeVar("T_co", covariant=True)


# TODO(135): https://github.com/pytorch/pytorch/issues/63095
def _in_batch_shuffle_fn(data: DataChunk):
    d = list(data)
    random.shuffle(d)
    return DataChunk(d)


@functional_datapipe("bucketbatch")
class BucketBatcherIterDataPipe(IterDataPipe[DataChunk[T_co]]):
    r""":class:`BucketBatcherIterDataPipe`.

    Iterable DataPipe to create mini-batches of data from sorted bucket. An outer
    dimension will be added as `batch_size` if `drop_last` is set to `True`,
    or `length % batch_size` for the last batch if `drop_last` is set to `False`.

    Args:
        datapipe: Iterable DataPipe being batched
        batch_size: The size of each batch
        drop_last: Option to drop the last batch if it's not full
        batch_num: Number of batches within a bucket (i.e. bucket_size = batch_size * batch_num)
        bucket_num: Number of buckets to consist a pool for shuffling (i.e. pool_size = bucket_size * bucket_num)
        sort_key: Callable to specify the comparison key for sorting within bucket
        in_batch_shuffle: Option to do in-batch shuffle or buffer shuffle
    """
    datapipe: IterDataPipe[T_co]
    batch_size: int
    drop_last: bool
    batch_num: int
    bucket_num: int
    sort_key: Optional[Callable]
    in_batch_shuffle: bool
    length: Optional[int]

    def __init__(
        self,
        datapipe: IterDataPipe[T_co],
        batch_size: int,
        drop_last: bool = False,
        batch_num: int = 100,
        bucket_num: int = 1,
        sort_key: Optional[Callable] = None,
        in_batch_shuffle: bool = True,
    ) -> None:
        assert batch_size > 0, "Batch size is required to be larger than 0!"
        assert batch_num > 0, "Number of batches is required to be larger than 0!"
        assert bucket_num > 0, "Number of buckets is required to be larger than 0!"
        super().__init__()

        # TODO(136): Verify _datapippe is not going to be serialized twice and is able to reconstruct
        self._datapipe: IterDataPipe[T_co] = datapipe
        self.batch_size: int = batch_size
        self.drop_last: bool = drop_last
        self.batch_num: int = batch_num
        self.bucket_num: int = bucket_num
        self.sort_key: Optional[Callable] = sort_key
        self.in_batch_shuffle: bool = in_batch_shuffle

        self.bucket_size = batch_size * batch_num
        self.pool_size = self.bucket_size * bucket_num

        # Shuffle by pool_size
        if bucket_num > 1 or sort_key is None:
            if in_batch_shuffle:
                datapipe = (
                    datapipe.batch(batch_size=self.pool_size, drop_last=False).map(fn=_in_batch_shuffle_fn).unbatch()
                )
            else:
                datapipe = datapipe.shuffle(buffer_size=self.pool_size)
        # Sort by bucket_size if sort_key is given
        if sort_key is not None:
            datapipe = datapipe.batch(self.bucket_size).map(fn=sort_key).unbatch()
        # Batch and drop last (if needed)
        datapipe = datapipe.batch(batch_size, drop_last=drop_last)
        # Shuffle the batched data
        if sort_key is not None:
            # In-batch shuffle each bucket seems not that useful
            if in_batch_shuffle:
                datapipe = datapipe.batch(batch_size=bucket_num, drop_last=False).map(fn=_in_batch_shuffle_fn).unbatch()
            else:
                datapipe = datapipe.shuffle(buffer_size=self.bucket_size)
        self.datapipe = datapipe
        self.length = None

    def __iter__(self) -> Iterator:
        yield from self.datapipe

    def __len__(self) -> int:
        if self.length is not None:
            return self.length
        if isinstance(self._datapipe, Sized):
            if self.drop_last:
                self.length = len(self._datapipe) // self.batch_size
            else:
                self.length = (len(self._datapipe) + self.batch_size - 1) // self.batch_size
            return self.length
        raise TypeError("{} instance doesn't have valid length".format(type(self).__name__))
