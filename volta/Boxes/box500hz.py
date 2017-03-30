""" 500Hz Volta Box
"""
import serial
import logging
import queue
import pandas as pd
import time
import numpy as np
from volta.common.interfaces import VoltaBox
from volta.common.util import Drain, TimeChopper

logger = logging.getLogger(__name__)


class VoltaBox500Hz(VoltaBox):
    def __init__(self, config):
        VoltaBox.__init__(self, config)
        self.grab_timeout = config.get('grab_timeout', 1)
        self.device = config.get('device', '/dev/cu.wchusbserial1420')
        self.sample_rate = 500
        self.baud_rate = 115200
        self.chop_ratio = config.get('chop_ratio', 1)
        self.data_source = serial.Serial(self.device, self.baud_rate, timeout=self.grab_timeout)
        logger.debug('Data source initialized: %s', self.data_source)

    def start_test(self, results):
        """ pipeline
                read source data ->
                chop by samplerate w/ ratio ->
                make pandas DataFrame ->
                drain DataFrame to queue `results`
        Args:
            results: object answers to put() and get() methods

        Returns:
            puts pandas DataFrame to specified queue
        """

        # clean up dirty buffer
        for _ in range(500):
            self.data_source.readline()

        self.reader = BoxPlainTextReader(
            self.data_source, self.sample_rate
        )
        self.pipeline = Drain(
            TimeChopper(
                self.reader, self.sample_rate, self.chop_ratio
            ),
            results
        )
        logger.info('Starting grab thread')
        self.pipeline.start()
        logger.info('Waiting grabber thread finish...')

    def end_test(self):
        self.reader.close()
        self.pipeline.close()
        self.pipeline.join(10)
        self.data_source.close()


def string_to_np(data):
    start_time = time.time()
    chunk = np.fromstring(data, dtype=float, sep='\n')
    logger.debug("Chunk decode time: %.2fms", (time.time() - start_time) * 1000)
    return chunk


class BoxPlainTextReader(object):
    """
    Read chunks from source, convert and return numpy.array
    """

    def __init__(self, source, cache_size=1024 * 1024 * 10):
        self.closed = False
        self.cache_size = cache_size
        self.source = source
        self.buffer = ""

    def _read_chunk(self):
        data = self.source.read(self.cache_size)
        if data:
            parts = data.rsplit('\n', 1)
            if len(parts) > 1:
                ready_chunk = self.buffer + parts[0] + '\n'
                self.buffer = parts[1]
                return string_to_np(ready_chunk)
            else:
                self.buffer += parts[0]
        else:
            self.buffer += self.source.readline()
        return None

    def __iter__(self):
        while not self.closed:
            yield self._read_chunk()
        yield self._read_chunk()

    def close(self):
        self.closed = True


# ==================================================

def main():
    logging.basicConfig(
        level="DEBUG",
        format='%(asctime)s [%(levelname)s] [Volta 500hz] %(filename)s:%(lineno)d %(message)s')
    logger.info("Volta 500 hz box ")
    cfg = {
        'device': '/dev/cu.wchusbserial1420'
    }
    worker = VoltaBox500Hz(cfg)
    logger.info('worker args: %s', worker.__dict__)
    q = queue.Queue()
    worker.start_test(q)
    time.sleep(10)
    logger.info('test finishing...')
    worker.end_test()
    logger.info('Queue size after test: %s', q.qsize())
    logger.info('Sample size: %s', q.get())
    logger.info('test finished')

if __name__ == "__main__":
    main()