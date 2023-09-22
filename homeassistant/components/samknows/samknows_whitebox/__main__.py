import asyncio
import logging
import os
from pprint import pprint
from dotenv import load_dotenv
import aiohttp
import pickle
import sys
import getopt

from . import api
from .logs import CustomFormatter

load_dotenv()

SK1_USERNAME: str = os.getenv("SK1_USERNAME")  # type:ignore
SK1_PASSWORD: str = os.getenv("SK1_PASSWORD")  # type:ignore
STORAGE_BUCKET_NAME = os.getenv("STORAGE_BUCKET_NAME")

# logging.root.setLevel(logging.DEBUG)

c_handler = logging.StreamHandler()
c_handler.setLevel(logging.DEBUG)
c_handler.setFormatter(CustomFormatter())

# Add handlers to the logger
logging.root.addHandler(c_handler)
logging.root.setLevel(logging.DEBUG)

_LOGGER = logging.getLogger(__name__)
# _LOGGER.critical("critical")
# _LOGGER.error("error")
# _LOGGER.warning("warning")
# _LOGGER.info("info")
# _LOGGER.debug("debug %s", UNIT_ANALYTICS_API_URL)


async def init(argv):
    force_fresh = False
    opts, args = getopt.getopt(argv, "f", ["force"])
    for opt, arg in opts:
        if opt in ("-f", "--force"):
            force_fresh = True

    async with aiohttp.ClientSession() as session:
        if os.path.exists(".tmp/api.pkl"):
            try:
                with open(".tmp/api.pkl", "rb") as file:
                    _LOGGER.debug("Creating API from pickle")
                    whitebox_api = pickle.load(file)
                    whitebox_api._session = session
                    whitebox_api._auth._session = session
            except IOError:
                os.remove(".tmp/api.pkl")
        else:
            _LOGGER.debug("Created new API")
            whitebox_api = api.WhiteboxApi(SK1_USERNAME, SK1_PASSWORD, session)
            await whitebox_api.login()

        units = await whitebox_api.fetch_user_units(force_fresh=force_fresh)

        latest_tests = await whitebox_api.fetch_scheduled_unit_tests(
            units[1]["unit_id"]
        )
        # current_data = latest_tests[0]

        # unit_stats = whitebox_api.fetch_unit_stats(unit_id)
        # unit_detailed_tests = whitebox_api.fetch_unit_tests(unit_id)

        # data = await whitebox_api.fetch_all_unit_updates()

        with open(".tmp/api.pkl", "wb") as file:
            pickle.dump(whitebox_api, file)
            _LOGGER.debug("Dumped API to pickle")

        pprint(units, width=80)
        pprint(latest_tests, width=80)


if __name__ == "__main__":
    asyncio.run(init(sys.argv[1:]))
