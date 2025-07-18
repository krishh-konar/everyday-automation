from requests import get, post
from requests.exceptions import HTTPError
from argparse import ArgumentParser
from bs4 import BeautifulSoup
from datetime import datetime
from re import search, match
from os import path, getenv
from collections import defaultdict
from urllib.parse import urlparse
from configparser import ConfigParser
from pprint import pformat
import asyncio
import telegram
import logging

# Setup Global variables for ease of usability
CLI_ARGS = None
CONFIG = None
LOGGER = None


def __bootstrap() -> None:
    """
    Setup required variable from config files and command line arguments.

    Raises:
        FileNotFoundError: Raises an Exception if config file is missing.
        AssertionError: Raises an exception if any required variables are missing.
    """
    global CLI_ARGS, CONFIG, LOGGER
    CLI_ARGS = __cli()

    logging.basicConfig(
        level=CLI_ARGS.log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    LOGGER = logging.getLogger(__name__)

    if CLI_ARGS.github_secrets:
        config_mode = "github_secrets"
    else:
        config_mode = "config_file"

    try:
        if config_mode == "config_file":
            # Read config from config file
            CONFIG = ConfigParser()
            if not path.exists(CLI_ARGS.file_path):
                raise FileNotFoundError
            CONFIG.read(CLI_ARGS.file_path)

        elif config_mode == "github_secrets":
            # Read config from environment variables
            CONFIG = {
                "MAIN": {
                    "WHAPI_API_URL": getenv("WHAPI_API_URL"),
                    "WHAPI_TOKEN": getenv("WHAPI_TOKEN"),
                    "WHAPI_GROUP_ID": getenv("WHAPI_GROUP_ID"),
                    "GMP_BASE_URL": getenv("GMP_BASE_URL"),
                }
            }

        else:
            LOGGER.error("No Config mode selected, exiting!")
            exit(-1)

        # check if required variables exist
        config_keys_to_check = ["WHAPI_API_URL", "WHAPI_TOKEN", "GMP_BASE_URL"]
        for key in config_keys_to_check:
            assert (
                key in CONFIG["MAIN"] and CONFIG["MAIN"][key] is not None
            ), f"{key} not found in config!"

    except AssertionError as e:
        LOGGER.error("Configuration Error: %s", e)
        exit(-1)
    except FileNotFoundError:
        LOGGER.error("Configuration file %s does not exist.", CLI_ARGS.file_path)
        exit(-1)
    except Exception as e:
        LOGGER.error("An exception occured in ConfigParser! : %s", e)
        exit(-1)


def __cli() -> ArgumentParser:
    """Bootstrap CLI for the script

    Returns:
        ArgumentParser: CLI arguments
    """
    parser = ArgumentParser(
        description="Send IPO application alerts to configured endpoints."
    )
    parser.add_argument(
        "-d",
        "--days-before-close",
        type=int,
        help="Number of days before the IPO application closes.",
        default=2,
    )
    parser.add_argument(
        "-t",
        "--alert-threshold",
        type=float,
        default=20.0,
        help="GMP threshold value; percentage above which to return IPOs.",
    )
    parser.add_argument(
        "-b",
        "--fallback-threshold",
        type=float,
        default=None,
        help="Fallback GMP threshold value; comes into place in case filtered"
        + "list has < 2 IPOs percentage above which to return IPOs.",
    )
    parser.add_argument(
        "-f",
        "--file-path",
        type=str,
        default=".config",
        help="Path to the config file (Default: ./.config).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Get IPO info without sending whatsapp message.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        type=str.upper,
        help="Set the logging level (default: INFO)",
    )

    # Adding mutually exclusive group for config modes
    config_type = parser.add_mutually_exclusive_group(required=False)
    config_type.add_argument(
        "--config-file",
        action="store_true",
        help="Use configuration from a file (default mode)",
    )
    config_type.add_argument(
        "--github-secrets",
        action="store_true",
        help="Use GitHub secrets for configuration",
    )

    return parser.parse_args()


def get_date_delta(date_str: str) -> int:
    """returns the difference between the ipo deadline date and the current date.

    Args:
        date_str (str): close date on the ipo

    Returns:
        int: difference b/w current and close date
    """
    date_format = "%d-%b-%Y"

    try:
        current_date = datetime.now().replace(second=0, hour=0, minute=0, microsecond=0)
        close_date = datetime.strptime(f"{date_str}-{current_date.year}", date_format)

        diff = close_date - current_date
        return diff.days

    except ValueError:
        return None


def parse_gmp(gmp_str: str) -> float:
    """returns percentage value for ipo gmp from the raw string

    Args:
        gmp_str (str): current predicted price and gmp percentage

    Returns:
        float: current ipo gmp percentage
    """

    # percentage value always in paranthesis
    pattern_match = search(r"\((\d+\.\d+)%\)", gmp_str)
    if pattern_match:
        percentage_str = pattern_match.group(1)
        return float(percentage_str)
    else:
        raise ValueError("Percentage not found in the string")


def fetch_ipo_data() -> dict:
    """Call IPO GMP page and parse IPO related data.

    Returns:
        dict: IPO data
    """
    try:
        response = get(url=CONFIG["MAIN"]["IPO_GMP_BASE_URL"])
    except HTTPError as e:
        LOGGER.error("Error fetching main site!")
        LOGGER.error(e)
        exit(-2)

    ipo_data = []
    base_url = urlparse(CONFIG["MAIN"]["GMP_BASE_URL"])
    hostname = f"{base_url.scheme}://{base_url.netloc}"

    raw_data = response.json()["reportTableData"]
    for row in raw_data:
        entry = defaultdict(str)

        if "SME" in row["~IPO_Category"].lower():
            entry["type"] = "sme"
        else:
            entry["type"] = "mainboard"

        # Extract the Name from the "title" attribute within the "~IPO_Name" field
        name_match = search(r'title="([^"]+)"', row["Name"])
        if name_match:
            entry["ipo_name"] = name_match.group(1).replace("IPO", "").strip()
        else:
            entry["ipo_name"] = row["Name"].replace("IPO", "").strip()

        # Extract GMP percentage value from the "~IPO_Name" field
        gmp_match = search(r"\((\d+\.\d+)%\)", row["Est Listing"])
        if gmp_match:
            entry["listing_gmp"] = float(gmp_match.group(1))
        else:
            entry["listing_gmp"] = None

        entry["close_date"] = row["Close"].strip()
        entry["ipo_url"] = hostname + row["~urlrewrite_folder_name"]
        ipo_data.append(entry)

    print(ipo_data)
    return ipo_data
    

def fetch_subscription_info(url: str) -> dict:
    """
    Fetches the subscription information for a given IPO from the
    subscriptions page and returns the latest day's subscription data.

    Args:
        url (str): URL for IPO's subscription page

    Returns:
        dict: Subscription info (eg. {"RII": "34.2x"})
    """

    # Url changes for subscriptions page from the original scrape
    url_root = CONFIG["MAIN"]["IPO_SUBSCRIPTION_BASE_URL"]
    url = url_root + url.split("/")[-2] 
    LOGGER.debug("Fetching subscription info from %s", url)

    try:
        response = get(url)
    except HTTPError as e:
        LOGGER.error("Error fetching subscription info for %s", url)
        LOGGER.error(e)
        return {}

    data = response.json()["data"]["ipoBiddingData"][-1]

    if len(data) == 0:
        LOGGER.error("Subscription table not found!")
        return {"upcoming": "Upcoming IPO, Subscription not open!"}

    resp = dict()
    resp["bidding_day"] = str(len(response.json()["data"]["ipoBiddingData"]))
    resp["RII"] = f"{data['rii']}x"
    resp["NII"] = f"{data['nii']}x"
    resp["QIB"] = f"{data['qib']}x"
    resp["Total"] = f"{data['total']}x"

    LOGGER.debug("Subscription Info for url: %s", url)
    LOGGER.debug("%s", resp)
    return resp



def extract_info(url: str) -> dict:
    """
    Fetches additional information for a given IPO from the
    IPO home page and returns the IPO's lot size and amount.

    Args:
        url (str): URL for IPO's subscription page

    Returns:
        dict: Additional Info about the IPO
    """
    try:
        url = url.replace("/gmp", "/ipo")
        response = get(url)
    except HTTPError as e:
        LOGGER.error("Error fetching additional ipo info for %s", url)
        LOGGER.error(e)
        return {}

    soup = BeautifulSoup(response.content, "html.parser")
    table_data = {}
    rows = soup.find_all("tr")

    for row in rows:
        columns = row.find_all("td")
        if len(columns) == 2:  # Check if the row has two columns
            key = columns[0].text.strip()
            value = columns[1].text.strip()
            print(f"Key: {key}, Value: {value}")
            if "Issue Price" in key:
                table_data["issue_price"] = value
            elif "1 Lot Amount" in key:
                table_data["lot_amount"] = value
            elif "Market Lot" in key:
                table_data["lot_size"] = value
            elif "IPO Issue Size" in key:
                table_data["issue_size"] = value
            elif "Individual Investor" in key:
                table_data["lot_amount"] = value

    return table_data


def get_filtered_list(ipo_data: list) -> tuple[list[dict], bool]:
    """
    Filter out IPOs matching the filtering criteria provided via CLI.
    Uses `filter_data()` to filter out IPOs. Initiates additional call
    to this function with fallback in case there are not enough IPOs.

    Args:
        ipo_data (dict): List of all IPOs

    Returns:
        tuple[list[dict], bool]: filtered IPOs and whether the
            fallback IPOs are included.
    """
    filtered_list = None
    gmp_threshold = CLI_ARGS.alert_threshold
    days_before_deadline = CLI_ARGS.days_before_close
    has_fallback_ipos = False

    filtered_list = filter_data(ipo_data, days_before_deadline, gmp_threshold)

    if len(filtered_list) < 2 and CLI_ARGS.fallback_threshold:
        # not enough IPOs and fallback is set to true, find more IPOs
        LOGGER.info(
            "Did not find enough IPOs and fallback is set, running with lower threshold."
        )
        has_fallback_ipos = True
        filtered_list = filter_data(
            ipo_data, days_before_deadline, CLI_ARGS.fallback_threshold
        )

    if LOGGER.level == "DEBUG":
        LOGGER.debug("Filtered List:")
        for item in filtered_list:
            LOGGER.debug(pformat(item))

    return (filtered_list, has_fallback_ipos)


def filter_data(
    ipo_data: list, days_before_deadline: int, threshold: float
) -> list[dict]:
    """
    Filter dictionaries matching given criteria

    Args:
        ipo_data (list): List of all IPOs
        days_before_deadline (int): Number of days before the IPO application closes
        threshold (float): GMP threshold value, percentage above which to return IPOs.

    Returns:
        list[dict]: filtered list of IPOs
    """
    filtered_list = []
    for ipo in ipo_data:
        if ipo["ipo_name"] == "":
            # handle edge cases for non IPO rows
            continue
        if ipo["close_date"] == "":
            LOGGER.debug("IPO close missing for %s, skipping!", ipo["ipo_name"])
            continue
        if ipo["listing_gmp"] == "--":
            LOGGER.debug("IPO gmp missing for %s, skipping!", ipo["ipo_name"])
            continue

        date_delta = get_date_delta(ipo["close_date"])
        if date_delta >= 0 and date_delta < days_before_deadline:
            try:
                if ipo["listing_gmp"] >= threshold:
                    # All checks pass, scrape the subscriptions page to fetch
                    # and add that information in ipo dict
                    ipo["ipo_subscription"] = fetch_subscription_info(ipo["ipo_url"])
                    ipo["ipo_info"] = extract_info(ipo["ipo_url"])
                    filtered_list.append(ipo)
            except Exception as e:
                LOGGER.error(
                    "Error parsing GMP for %s: %s, skipping!", ipo["ipo_name"], e
                )

    print(f"Filtered IPOs: {filtered_list}")
    return filtered_list


def format_msg(msg: list, has_fallback_ipos: bool) -> str:
    """Format the message to be sent to whatsapp from list of IPOs

    Args:
        msg (list): List of IPOs
        has_fallback_ipos (bool): IPO list contains fallback IPOs

    Returns:
        str: Whatsapp message to be sent
    """
    if not msg:
        return ""

    formatted_str = f"*IPO Alerts for the next {CLI_ARGS.days_before_close} days*\n\n"

    if has_fallback_ipos:
        formatted_str += (
            "*Attention*: Did not find enough IPOs and fallback is set, "
            + f"showing IPOs with *lower GMPs of > {CLI_ARGS.fallback_threshold}%*.\n\n"
        )

    for ipo_type in ["mainboard", "sme"]:
        if any(entry["type"] == ipo_type for entry in msg):
            ipo_type_header = f"*{ipo_type.upper()} IPOs:*\n"
            formatted_str += ipo_type_header
            formatted_str += "-" * len(ipo_type_header) + "\n\n"

        for line in msg:
            if line["type"] is not ipo_type:
                continue

            formatted_str += f"*‣ {line['ipo_name']}*\n"
            formatted_str += f"> GMP: *{line['listing_gmp']}%*\n"
            formatted_str += f"> Issue Size: *{line['ipo_info']['issue_size']}*\n"
            formatted_str += f"> Issue Price: *{line['ipo_info']['issue_price']}*\n"
            formatted_str += f"> Lot Size: *{line['ipo_info']['lot_size']}*\n"
            formatted_str += f"> Lot Amount: *{line['ipo_info']['lot_amount']}*\n"
            formatted_str += f"> Closing On: *{line['close_date']}*\n"

            if "upcoming" not in line["ipo_subscription"].keys():
                formatted_str += f"Subscription Info *(Day {line['ipo_subscription']['bidding_day']})*:\n> "

                for institution in line["ipo_subscription"].keys():
                    if institution == "bidding_day":
                        continue

                    formatted_str += (
                        f"*{institution}*: {line['ipo_subscription'][institution]}, "
                    )

                formatted_str = formatted_str[:-2]

            else:
                formatted_str += (
                    f"Subscription Info:\n> {line['ipo_subscription']['upcoming']}"
                )

            formatted_str += "\n\n"

    return formatted_str


### WHAPI Methods ###
#####################


def create_group(users: list) -> str:
    """Create a whatsapp group using WHAPI.
    Probably one time use (fetch group_id from there for later use).

    Args:
        users (list): List of Phone numbers to add to the group.

    Returns:
        str: WHAPI response
    """
    url = "https://gate.whapi.cloud/groups"

    payload = {"subject": "IPO Alerts", "participants": users}
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {CONFIG['MAIN']['WHAPI_TOKEN']}",
    }

    response = post(url, json=payload, headers=headers)

    LOGGER.debug(response.text)
    return response.text


def add_user_to_group(users: list) -> str:
    """
    Add user to an already existing group.
    Requires `group_id`.

    Args:
        users (list): List of Phone numbers to add to the group.

    Returns:
        str: WHAPI response
    """
    url = f"https://gate.whapi.cloud/groups/{CONFIG['MAIN']['WHAPI_GROUP_ID']}/participants"

    payload = {"participants": users}
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {CONFIG['MAIN']['WHAPI_TOKEN']}",
    }

    response = post(url, json=payload, headers=headers)

    LOGGER.debug(response.text)
    return response.text


def send_message(msg: str) -> str:
    """
    Send a message to a given whatsapp group.
    Requires `group_id`.

    Args:
        msg (str): Whatsapp message to be sent.

    Returns:
        str: WHAPI response
    """
    url = "https://gate.whapi.cloud/messages/text"

    payload = {"typing_time": 0, "to": CONFIG["MAIN"]["WHATSAPP_GROUP_ID"], "body": msg}
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {CONFIG['MAIN']['WHAPI_TOKEN']}",
    }

    response = post(url, json=payload, headers=headers)

    LOGGER.debug(response.text)
    return response.text

def send_message_green_api(msg: str) -> str:
    """
    Send a message to a given whatsapp group using Green API.
    Requires `group_id`.

    Args:
        msg (str): Whatsapp message to be sent.

    Returns:
        str: Green API response
    """
    api_creds = CONFIG["GREENAPI"]
    url = f"{api_creds['API_URL']}/waInstance{api_creds['ID_INSTANCE']}/sendMessage/{api_creds['API_TOKEN']}"


    payload = {
        "chatId": CONFIG["MAIN"]["WHATSAPP_GROUP_ID"],
        "message": msg,
        }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
    }

    response = post(url, json=payload, headers=headers)

    LOGGER.debug(response.text)
    return response.text

def init_telegram_bot() -> telegram.Bot:
    """
    Initialize the Telegram bot using the token from the config.

    Returns:
        telegram.Bot: Initialized Telegram bot instance.
    """
    token = CONFIG["TELEGRAM"]["TOKEN"]
    if not token:
        LOGGER.error("Telegram bot token not found in config!")
        exit(-1)

    try:
        bot = telegram.Bot(token=token)
        return bot
    
    except Exception as e:
        LOGGER.error("Failed to initialize Telegram bot: %s", e)
        exit(-1)

async def send_message_telegram(bot: telegram.Bot, msg: str) -> None:
    """
    Send a message to the Telegram bot.

    Args:
        bot (telegram.Bot): Initialized Telegram bot instance.
        msg (str): Message to be sent.
    """
    try:
        await bot.send_message(chat_id=CONFIG["TELEGRAM"]["CHAT_ID"], text=msg, parse_mode="Markdown")
        LOGGER.info("Message sent to Telegram successfully.")
    except Exception as e:
        LOGGER.error("Failed to send message to Telegram: %s", e)

async def main():
    __bootstrap()

    # Enable for first time-run
    #
    # initial_users = ["<Phone Numbers>"]
    # resp = create_group(initial_users)
    # LOGGER.info(resp)

    ipo_data = fetch_ipo_data()
    ipo_alerts_data, has_fallback_ipos = get_filtered_list(ipo_data)
    message = format_msg(ipo_alerts_data, has_fallback_ipos)
    telegram_bot = init_telegram_bot()

    if message:
        LOGGER.info(message)
    else:
        LOGGER.info("No upcoming IPOs with matching criteria!")

    if not CLI_ARGS.dry_run and message:
        send_message_telegram(telegram_bot, message)
        return


if __name__ == "__main__":
    asyncio.run(main())
