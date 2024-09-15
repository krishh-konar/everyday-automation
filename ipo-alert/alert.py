from requests import get as get_url
from argparse import ArgumentParser
from bs4 import BeautifulSoup
from datetime import datetime
from re import search


GMP_BASE_URL = "https://www.investorgain.com/report/live-ipo-gmp/331/"

def cli() -> ArgumentParser:
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

    except ValueError as e:
        print(f"Error parsing date: {e}")
        return None

def parse_gmp(gmp_str: str) -> float:
    """returns percentage value for ipo gmp from the raw string

    Args:
        gmp_str (str): current predicted price and gmp percentage

    Returns:
        float: current ipo gmp percentage
    """

    # percentage value always in paranthesis
    match = search(r'\((\d+\.\d+)%\)', gmp_str)
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
    response = get_url(GMP_BASE_URL)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")

        ipo_data = []

        # Data present in elements with data-label="IPO", "Est Listing", and "Close"
        ipo_name_elements = soup.find_all(attrs={"data-label": "IPO"})
        listing_gmp_elements = soup.find_all(attrs={"data-label": "Est Listing"})
        close_date_elements = soup.find_all(attrs={"data-label": "Close"})

        # Check if the number of IPO, Est Listing, and Close elements match, assertion should be true.
        if len(ipo_name_elements) == len(listing_gmp_elements) == len(close_date_elements):
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
            print("The number of IPO, listing GMP and close date elements do not match.")
    else:
        print(f"Failed to retrieve the page. Status code: {response.status_code}")

    return ipo_data


def filter_data(cli_args: ArgumentParser, ipo_data: list) -> dict:
    """
    Filter out IPOs matching the filtering criteria provided via CLI

    Args:
        cli_args (ArgumentParser): CLI args
        ipo_data (dict): All available IPOs data 

    Returns:
        dict: filtered IPOs
    """    
    filtered_list = []
    gmp_threshold = cli_args.alert_threshold
    days_before_deadline = cli_args.days_before_close

    for ipo in ipo_data:
        date_delta = get_date_delta(ipo["close_date"])
        if date_delta and date_delta >= 0 and date_delta < days_before_deadline:
            if parse_gmp(ipo["listing_gmp"]) >= gmp_threshold:
                filtered_list.append(ipo)

    return filtered_list


def main():
    args = cli()
    ipo_data = fetch_ipo_data()
    ipo_alerts_data = filter_data(args, ipo_data)
    for ipo in ipo_alerts_data:
        print(ipo)
    


if __name__ == "__main__":
    main()
