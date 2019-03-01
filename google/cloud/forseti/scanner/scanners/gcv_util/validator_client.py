import sys
from retrying import retry

from google.cloud.forseti.common.util import retryable_exceptions
from google.cloud.forseti.scanner.scanners.gcv_util import validator_pb2
from google.cloud.forseti.scanner.scanners.gcv_util import validator_pb2_grpc


class ValidatorClient(object):
    """Validator client."""

    DEFAULT_CHANNEL = 'localhost:50052'

    def __init__(self, channel=DEFAULT_CHANNEL):
        """Initialize

        Args:
            channel (String): The default Validator channel.
        """
        self.buffer_sender = BufferedGCVDataSender(self)
        self.stub = validator_pb2_grpc.ValidatorStub(channel)

    @retry(retry_on_exception=retryable_exceptions.is_retryable_exception_grpc,
           wait_exponential_multiplier=1000, wait_exponential_max=10000,
           stop_max_attempt_number=5)
    def add_data(self, assets):
        """Add asset data.

        Args:
            assets (list): A list of asset data.
        """
        request = validator_pb2.AddDataRequest(assets=assets)
        self.stub.AddData(request)

    def add_data_to_buffer(self, asset):
        """Add asset data to buffer, intended to manage sending data in bulk.

        Args:
            asset (Asset): The asset data.
        """
        self.buffer_sender.add(asset)

    def flush_buffer(self):
        """Flush the buffer, sending all the data to
        GCV and empty the buffer."""
        self.buffer_sender.flush()

    @retry(retry_on_exception=retryable_exceptions.is_retryable_exception_grpc,
           wait_exponential_multiplier=1000, wait_exponential_max=10000,
           stop_max_attempt_number=5)
    def audit(self):
        """Audit existing data in GCV.

        Returns:
            list: List of violations.
        """
        self.stub.Audit()

    @retry(retry_on_exception=retryable_exceptions.is_retryable_exception_grpc,
           wait_exponential_multiplier=1000, wait_exponential_max=10000,
           stop_max_attempt_number=5)
    def reset(self):
        """Clears previously added data from GCV."""
        self.stub.Reset()


class BufferedGCVDataSender(object):
    """Buffered GCV data sender."""

    MAX_ALLOWED_PACKET = 4000000  # Default grpc message size limit is 4MB.

    def __init__(self,
                 validator_client,
                 max_size=1024,
                 max_packet_size=MAX_ALLOWED_PACKET * .75):
        """Initialize.

        Args:
            validator_client (ValidatorClient): The validator client.
            max_size (int): max size of buffer.
            max_packet_size (int): max size of a packet to send to GCV.
        """
        self.validator_client = validator_client
        self.buffer = []
        self.packet_size = 0
        self.max_size = max_size
        self.max_packet_size = max_packet_size

    def add(self, asset):
        """Add an Asset to the buffer to send to GCV.

        Args:
            asset (Asset): Asset to send to GCV.
        """

        self.buffer.append(asset)
        self.packet_size += sys.getsizeof(asset)
        if (self.packet_size > self.max_packet_size or
                len(self.buffer) >= self.max_size):
            self.flush()

    def flush(self):
        """Flush all pending objects to the database."""
        self.validator_client.add_data(self.buffer)
        self.buffer = []
        self.packet_size = 0