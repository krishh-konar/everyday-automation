from requests import get, post
from argparse import ArgumentParser
from bs4 import BeautifulSoup
from datetime import datetime
from re import search, match
from os import path, getenv
from collections import defaultdict
from urllib.parse import urlparse
from configparser import ConfigParser
from pprint import pformat
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
        help="Fallback GMP threshold value; comes into place in case filtered" + \
            "list has < 2 IPOs percentage above which to return IPOs.",
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
        current_date = datetime.now()
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
    response = get(url=CONFIG["MAIN"]["GMP_BASE_URL"])

    # the urls we get are relavtive urls, will need to append the hostname
    base_url = urlparse(CONFIG["MAIN"]["GMP_BASE_URL"])
    hostname = f"{base_url.scheme}://{base_url.netloc}"

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        ipo_data = []

        rows = soup.find_all("tr")  # scan all rows

        for row in rows:
            entry = defaultdict(str)

            # Data present in elements with data-label="IPO", "Est Listing", and "Close"
            ipo_tag = row.find("td", attrs={"data-label": "IPO"})
            if ipo_tag:
                # Find the <a> tag within this td to get the URL and name
                ipo_link = ipo_tag.find("a")
                if ipo_link:
                    entry["ipo_url"] = hostname + ipo_link["href"]
                    for span in ipo_link.find_all("span"):
                        span.decompose()
                    entry["ipo_name"] = ipo_link.get_text(strip=True)

            est_listing_tag = row.find("td", attrs={"data-label": "Est Listing"})
            if est_listing_tag:
                entry["listing_gmp"] = est_listing_tag.text.strip()

            close_tag = row.find("td", attrs={"data-label": "Close"})
            if close_tag:
                entry["close_date"] = close_tag.text.strip()

            ipo_data.append(entry)

    else:
        LOGGER.error(
            "Failed to retrieve the page. Status code: %s", response.status_code
        )

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
    url = url.replace("/gmp", "/subscription")

    response = get(url)
    html_content = response.text
    soup = BeautifulSoup(html_content, "html.parser")
    table = None

    # The table has no real attribute to pinpoint it on page,
    # so using the "caption" tag to find the table.
    for caption in soup.find_all("caption"):
        if caption.text.strip() == "IPO Bidding Live Updates from BSE + NSE":
            table = caption.find_parent("table")
            break

    if not table:
        LOGGER.error("Subscription table not found!")
        return {"upcoming": "Upcoming IPO, Subscription not open!"}

    # Get all rows within the table
    rows = table.find_all("tr")

    if not rows:
        LOGGER.error("No rows found in the table")
        return {"upcoming": "Upcoming IPO, Subscription not open!"}

    # Only get the last row, for the latest subscription info.
    last_row = rows[-1]

    # Extract data-title attributes and their corresponding text from the last row
    last_row_data = {}
    cells = last_row.find_all("td")

    # ignoring the first two columns (date and serial)
    for cell in cells[2:]:
        data_title = cell.get("data-title")
        if data_title:
            # Seperate institution and Date
            pattern = r"(.*)-Day(\d+)"
            institution = match(pattern, data_title)

            if institution:
                last_row_data["bidding_day"] = institution.group(2)
                last_row_data[institution.group(1)] = cell.text.strip()

    LOGGER.debug("Subscription Info for url: %s", url)
    LOGGER.debug("%s", last_row_data)
    return last_row_data


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
        if date_delta and date_delta >= 0 and date_delta < days_before_deadline:
            if parse_gmp(ipo["listing_gmp"]) >= threshold:
                # All checks pass, scrape the subscriptions page to fetch 
                # and add that information in ipo dict
                ipo_subscription = fetch_subscription_info(ipo["ipo_url"])
                ipo["ipo_subscription"] = ipo_subscription
                filtered_list.append(ipo)

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
        formatted_str += "*Attention*: Did not find enough IPOs and fallback is set, " + \
            f"showing IPOs with *lower GMPs of > {CLI_ARGS.fallback_threshold}%*.\n\n"

    for line in msg:
        formatted_str += f"*‣ {line['ipo_name']}*\n"
        formatted_str += f"> GMP: *{line['listing_gmp']}*\n"
        formatted_str += f"> Closing On: *{line['close_date']}*\n"

        if not line["ipo_subscription"]["upcoming"]:
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

    payload = {"typing_time": 0, "to": CONFIG["MAIN"]["WHAPI_GROUP_ID"], "body": msg}
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {CONFIG['MAIN']['WHAPI_TOKEN']}",
    }

    response = post(url, json=payload, headers=headers)

    LOGGER.debug(response.text)
    return response.text


def main():
    __bootstrap()

    # Enable for first time-run
    #
    # initial_users = ["<Phone Numbers>"]
    # resp = create_group(initial_users)
    # LOGGER.info(resp)

    ipo_data = fetch_ipo_data()
    ipo_alerts_data, has_fallback_ipos = get_filtered_list(ipo_data)
    message = format_msg(ipo_alerts_data, has_fallback_ipos)

    if message:
        LOGGER.info(message)
    else:
        LOGGER.info("No upcoming IPOs with matching criteria!")

    if not CLI_ARGS.dry_run and message:
        send_message(message)
        return


if __name__ == "__main__":
    main()
