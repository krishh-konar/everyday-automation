from requests import get as get_url
from argparse import ArgumentParser
from bs4 import BeautifulSoup

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
        ipo_elements = soup.find_all(attrs={"data-label": "IPO"})
        est_listing_elements = soup.find_all(attrs={"data-label": "Est Listing"})
        close_elements = soup.find_all(attrs={"data-label": "Close"})

        # Check if the number of IPO, Est Listing, and Close elements match, assertion should be true.
        if len(ipo_elements) == len(est_listing_elements) == len(close_elements):
            for ipo_element, est_listing_element, close_element in zip(
                ipo_elements, est_listing_elements, close_elements
            ):
                # Find the <a> tag with target="_parent" within each IPO element
                a_tag = ipo_element.find("a", attrs={"target": "_parent"})
                if a_tag:
                    # Remove all <span> tags from the <a> tag's contents, this contains additional listing data
                    for span in a_tag.find_all("span"):
                        span.decompose()
                    ipo_value = a_tag.get_text(strip=True)
                else:
                    ipo_value = None

                est_listing_value = est_listing_element.get_text(strip=True)
                close_value = close_element.get_text(strip=True)

                entry = {
                    "IPO": ipo_value,
                    "Est_listing": est_listing_value,
                    "Close": close_value,
                }
                ipo_data.append(entry)

            for item in ipo_data:
                print(item)
        else:
            print("The number of IPO, Est Listing, and Close elements do not match.")
    else:
        print(f"Failed to retrieve the page. Status code: {response.status_code}")

    return ipo_data


def filter_data(cli_args: ArgumentParser, ipo_data: dict) -> dict:
    """
    Filter out IPOs matching the filtering criteria provided via CLI

    Args:
        cli_args (ArgumentParser): CLI args
        ipo_data (dict): All available IPOs data 

    Returns:
        dict: filtered IPOs
    """    
    filtered_list = {}

    return filter_data


def main():
    args = cli()
    print(args)
    # ipo_data = fetch_ipo_data()


if __name__ == "__main__":
    main()
