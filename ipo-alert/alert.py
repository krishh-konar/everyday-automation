from requests import get as get_url
from argparse import ArgumentParser
from bs4 import BeautifulSoup

GMP_BASE_URL = "https://www.investorgain.com/report/live-ipo-gmp/331/"


def cli() -> ArgumentParser:
    """
        Bootstrap CLI
    """
    parser = ArgumentParser(description="Extract IPO data from the given URL.")
    parser.add_argument('url', type=str, help="The URL of the page to scrape.")
    parser.add_argument('days_before_deadline', type=int, help="Number of days before the deadline.")
    parser.add_argument('gmp_threshold', type=float, help="GMP threshold value.")
    
    return parser.parse_args()


def fetch_ipo_data():
    """
        Call IPO GMP page and parse IPO related data.
    """
    response = get_url(GMP_BASE_URL)

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')

        ipo_data = []

        # Data present in elements with data-label="IPO", "Est Listing", and "Close"
        ipo_elements = soup.find_all(attrs={"data-label": "IPO"})
        est_listing_elements = soup.find_all(attrs={"data-label": "Est Listing"})
        close_elements = soup.find_all(attrs={"data-label": "Close"})

        # Check if the number of IPO, Est Listing, and Close elements match, assertion should be true.
        if len(ipo_elements) == len(est_listing_elements) == len(close_elements):
            for ipo_element, est_listing_element, close_element in zip(ipo_elements, est_listing_elements, close_elements):
                # Find the <a> tag with target="_parent" within each IPO element
                a_tag = ipo_element.find('a', attrs={"target": "_parent"})
                if a_tag:
                    # Remove all <span> tags from the <a> tag's contents
                    for span in a_tag.find_all('span'):
                        span.decompose()
                    ipo_value = a_tag.get_text(strip=True)
                else:
                    ipo_value = None

                # Extract text for Est Listing and Close, ignoring <span> tags
                est_listing_value = est_listing_element.get_text(strip=True)
                close_value = close_element.get_text(strip=True)

                # Create a dictionary with the extracted values
                entry = {
                    "IPO": ipo_value,
                    "Est_listing": est_listing_value,
                    "Close": close_value
                }
                ipo_data.append(entry)

            for item in ipo_data:
                print(item)
        else:
            print("The number of IPO, Est Listing, and Close elements do not match.")
    else:
        print(f"Failed to retrieve the page. Status code: {response.status_code}")


def main():
    args = cli()
    print(args)


if __name__ == "__main__":
    main()
