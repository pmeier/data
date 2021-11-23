import io
import os.path
from typing import Tuple, Iterator

from torchdata.datapipes.utils import StreamWrapper
from torchdata.datapipes import functional_datapipe
from torchdata.datapipes.iter import IterDataPipe
from torchdata.datapipes.utils.common import validate_pathname_binary_tuple


@functional_datapipe("load_from_rar")
class RarArchiveLoaderIterDataPipe(IterDataPipe[Tuple[str, io.BufferedIOBase]]):
    def __init__(self, datapipe: IterDataPipe[Tuple[str, io.BufferedIOBase]]):
        self._rarfile = self._verify_dependencies()
        super().__init__()
        self.datapipe = datapipe

    def _verify_dependencies(self):
        try:
            import rarfile
        except ImportError as error:
            raise ModuleNotFoundError(
                "Package `rarfile` is required to be installed to use this datapipe. "
                "Please use `pip install rarfile` or `conda -c conda-forge install rarfile` to install it."
            ) from error

        # check if at least one system library for reading rar archives is available to be used by rarfile
        rarfile.tool_setup()

        return rarfile

    def __iter__(self) -> Iterator[Tuple[str, io.BufferedIOBase]]:
        for data in self.datapipe:
            validate_pathname_binary_tuple(data)
            path, stream = data
            rar = self._rarfile.RarFile(stream)
            for info in rar.infolist():
                if info.filename.endswith("/"):
                    continue

                inner_path = os.path.join(path, info.filename)
                file_obj = rar.open(info)

                yield inner_path, StreamWrapper(file_obj)  # type: ignore[misc]
