import sys
import redis
import logging

# logger for this file
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('/tmp/tracker.log')
handler.setLevel(logging.ERROR)
formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class RedisDB:
    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.db = redis.Redis(host=self.host, port=self.port, password=self.password)
        self.test_connection()

    def test_connection(self):
        try:
            self.db.ping()
        except Exception as e:
            logging.critical("Redis connection Error")
            logging.critical(e)
            sys.exit(-1)

    def get(self, key):
        result = self.db.get(name=key)
        return result

    def set(self, key, value, ttl=-1):
        if ttl > 0:
            self.db.set(name=key, value=value, keepttl=ttl)
        self.db.set(name=key, value=value)

    def publish(self):
        pass

    def subscribe(self):
        pass
