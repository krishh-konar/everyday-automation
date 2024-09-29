# Send IPO Alerts

[![Run IPO Alerts Cron](https://github.com/krishh-konar/everyday-automation/actions/workflows/cron.yml/badge.svg)](https://github.com/krishh-konar/everyday-automation/actions/workflows/cron.yml)

This script fetches subscription information for upcoming IPOs to be listed on NSE/BSE and sends alerts.
Uses data from [Investor Gain](https://www.investorgain.com/report/live-ipo-gmp/331/) and [Whapi](https://whapi.cloud/) to send whatsapp messages.

## Instructions

* Follow the First time Run rules to setup the required variables.
* Install required dependencies using `pip install -r requirements.txt`. (A virtual environment is recommended).
* Run script with required parameters (`-d` and `-t`).

``` bash
$ python alert.py -d 3 -t 25
$ python alert.py --days-before-close 3 --alert-threshold 25
```

* There are 2 possible ways to pass config variables: config file and github secrets.
  * Config File is the default (and preferred) way to run the script from local machine.
    eg. `$ python alert.py -d 3 -t 25`
    or `$ python alert.py -f /path/to/.config -d 3 -t 25`
  * The second method is using github secrets. This fetches the required config variables from Github secrets and is mainly implemented to use github's `schedule` workflow to run the script once a day.

    ``` bash
    $ python script.py --github-secrets --days-before-close 5 --alert-threshold 15.0
    ```

### First Time Run

* Rename `.config.sample` to `.config` and add required tokens/credentials before running.
* This uses [WHAPI](https://whapi.cloud/) to send messages to whatsapp. Create an account here to get required authorization token.
* [Optional] A `group_id` is needed to send alert to a particular group. You can use `create_group()` method to get the `group_id` from whapi and add that to your `.config`.
