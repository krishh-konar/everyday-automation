from requests import get, post
from argparse import ArgumentParser
from bs4 import BeautifulSoup
from datetime import datetime
from re import search
from os import path, getenv
from configparser import ConfigParser


# Setup Global variables for ease of usability
CLI_ARGS = None
CONFIG = None


def __bootstrap() -> None:
    """
    Setup required variable from config files and command line arguments.

    Raises:
        FileNotFoundError: Raises an Exception if config file is missing.
        AssertionError: Raises an exception if any required variables are missing.
    """
    global CLI_ARGS, CONFIG
    CLI_ARGS = __cli()

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
                    "WHAPI_API_URL": getenv("MY_SECRET"),
                    "WHAPI_TOKEN": getenv("WHAPI_TOKEN"),
                    "WHAPI_GROUP_ID": getenv("WHAPI_GROUP_ID"),
                    "GMP_BASE_URL": getenv("GMP_BASE_URL"),
                }
            }

        else:
            print("No Config mode selected, exiting!")
            exit(-1)

        print(CLI_ARGS.config_file, CLI_ARGS.github_secrets)
        print(CONFIG["MAIN"]["GMP_BASE_URL"])
        # check if required variables exist
        config_keys_to_check = ["WHAPI_API_URL", "WHAPI_TOKEN", "GMP_BASE_URL"]
        for key in config_keys_to_check:
            assert (
                key in CONFIG["MAIN"] and CONFIG["MAIN"][key] is not None
            ), f"{key} not found in config!"

    except AssertionError as e:
        print(f"Configuration Error: {e}")
        exit(-1)
    except FileNotFoundError:
        print(f"Configuration file {CLI_ARGS.file_path} does not exist.")
        exit(-1)
    except Exception as e:
        print(f"An exception occured in ConfigParser! : {e}")
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
    match = search(r"\((\d+\.\d+)%\)", gmp_str)
    if match:
        percentage_str = match.group(1)
        return float(percentage_str)
    else:
        raise ValueError("Percentage not found in the string")


def fetch_ipo_data() -> dict:
    """Call IPO GMP page and parse IPO related data.

    Returns:
        dict: IPO data
    """
    response = get(CONFIG["MAIN"]["GMP_BASE_URL"])

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")

        ipo_data = []

        # Data present in elements with data-label="IPO", "Est Listing", and "Close"
        ipo_name_elements = soup.find_all(attrs={"data-label": "IPO"})
        listing_gmp_elements = soup.find_all(attrs={"data-label": "Est Listing"})
        close_date_elements = soup.find_all(attrs={"data-label": "Close"})

        # Check if the number of IPO, Est Listing, and Close elements match, assertion should be true.
        if (
            len(ipo_name_elements)
            == len(listing_gmp_elements)
            == len(close_date_elements)
        ):
            for ipo_name_element, listing_gmp_element, close_date_element in zip(
                ipo_name_elements, listing_gmp_elements, close_date_elements
            ):
                # Find the <a> tag with target="_parent" within each IPO element
                a_tag = ipo_name_element.find("a", attrs={"target": "_parent"})
                if a_tag:
                    # Remove all <span> tags from the <a> tag's contents, this contains additional listing data
                    for span in a_tag.find_all("span"):
                        span.decompose()
                    ipo_name = a_tag.get_text(strip=True)
                else:
                    ipo_name = None

                listing_gmp = listing_gmp_element.get_text(strip=True)
                close_date = close_date_element.get_text(strip=True)

                entry = {
                    "ipo_name": ipo_name,
                    "listing_gmp": listing_gmp,
                    "close_date": close_date,
                }
                ipo_data.append(entry)

        else:
            print(
                "The number of IPO, listing GMP and close date elements do not match."
            )
    else:
        print(f"Failed to retrieve the page. Status code: {response.status_code}")

    return ipo_data


def filter_data(ipo_data: list) -> dict:
    """
    Filter out IPOs matching the filtering criteria provided via CLI

    Args:
        cli_args (ArgumentParser): CLI args
        ipo_data (dict): All available IPOs data

    Returns:
        dict: filtered IPOs
    """
    filtered_list = []
    gmp_threshold = CLI_ARGS.alert_threshold
    days_before_deadline = CLI_ARGS.days_before_close

    for ipo in ipo_data:
        date_delta = get_date_delta(ipo["close_date"])
        if date_delta and date_delta >= 0 and date_delta < days_before_deadline:
            if parse_gmp(ipo["listing_gmp"]) >= gmp_threshold:
                filtered_list.append(ipo)

    return filtered_list


def format_msg(msg: list) -> str:
    """Format the message to be sent to whatsapp from list of IPOs

    Args:
        msg (list): List of IPOs

    Returns:
        str: Whatsapp message to be sent
    """
    formatted_str = f"*IPO Alerts for the next {CLI_ARGS.days_before_close} days*\n\n"

    for line in msg:
        formatted_str += f"‣ {line['ipo_name']}\n"
        formatted_str += f"> GMP: *{line['listing_gmp']}*\n"
        formatted_str += f"> Closing On: *{line['close_date']}*\n"
        formatted_str += "\n"

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

    return response.text


def main():
    __bootstrap()

    # Enable for first time-run
    #
    # initial_users = ["<Phone Numbers>"]
    # resp = create_group(initial_users)
    # print(resp)

    ipo_data = fetch_ipo_data()
    ipo_alerts_data = filter_data(ipo_data)
    for ipo in ipo_alerts_data:
        print(ipo)
    message = format_msg(ipo_alerts_data)
    if not CLI_ARGS.dry_run:
        send_message(message)


if __name__ == "__main__":
    main()
