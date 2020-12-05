# ffbe_forever_guild_bot
A bot for the War of the Visions guild, FFBEForever

Helpful Links:
* https://discord.com/developers/applications
* https://discordpy.readthedocs.io/en/latest/intro.html

Steps to prep your environment to work on or run this bot:
```
sudo apt-get update
sudo apt-get install python3-distutils python3.7-venv libgl1-mesa-glx tesseract-ocr
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
sudo python3.7 get-pip.py
python3.7 -m venv bot-env
source bot-env/bin/activate
pip install --upgrade pip
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib pytesseract numpy imutils opencv-python opencv-contrib-python discord.py
```

You will also need to clone a copy of the War of the Visions data dump github project at https://github.com/shalzuth/wotv-ffbe-dump. Make note of the path where this is located.

After checkout, and whenever you want to run the bot:
```
python3 -m venv bot-env
source bot-env/bin/activate
```

Now configure the bot to connect to discord:
* Visit https://discordpy.readthedocs.io/en/latest/discord.html and follow instructions to create your bot on Discord. Make a note of your token.
* Back in the Discord console, generate your invite link. Make sure to give the following permissions in the invite URL:
  * Send Messages
  * Embed Links
  * Read Message History (future expansion)
  * Add Reactions (future expansion)
  * The permissions above can be abbreviated in the URL as 84032.
* Use the invitation link to invite the bot to a server that you have the authority to add it to.
  * It's probably best to make your own private server first and test everything out.

Now we prepare to connect to Google
* Visit https://developers.google.com/sheets/api/quickstart/python and follow instructions to create an OAuth app.
* When prompted how to configure, choose "Desktop Application"
* Download the credentials file and place it in the checkout directory. Rename it to google_credentials.json
* In your python virtual environment:
```pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib```

Now we will create the config file ```bot_config.json``` in the same directory as the source code. Here we will set the Google spreadsheet you want the bot to manage, as well as the ID of a sandbox for trying out potentially-problematic commands like adding espers and units. Also add the ID of the administrative spreadsheet where you will bind Discord Snowflake IDs to guild aliases (used as tab names in the Resonance spreadsheet), and where you can set admin rights and the Discord bot token from earlier. Here is a sample ```bot_config.json```:
```
{
  "esper_resonance_spreadsheet_id": "your_google_spreadsheet_id_here",
  "sandbox_esper_resonance_spreadsheet_id": "your_google_spreadsheet_id_here",
  "vision_card_spreadsheet_id": "your_vision_card_google_spreadsheet_id_here",
  "access_control_spreadsheet_id": "your_google_spreadsheet_id_here",
  "discord_bot_token": "your_discord_bot_token_here",
  "data_dump_root_path": "path/to/your/wotv-ffbe-dump/"
}
```

You're ready to start now. Start the bot using the following commands  (or run the convenience script [run_bot.sh](run_bot.sh), which does the same thing):
```
python3 -m venv bot-env
source bot-env/bin/activate
python3 ffbe_forever_guild_bot.py
```
You will be prompted to visit a URL to authorize the bot for the first time. Do so. That's it! The bot should be up and running now.


## The Access Control spreadsheet

This spreadsheet gates write access to writes, ensuring that a user can only modify their own data. Use the bot's hidden commands !whois <username> and !whoami to get the snowflake IDs. Populate three columns:
* Column A: Snowflake ID. Put the raw snowflake IDs in this column.
* Column B: Alias. For each Snowflake ID, put the alias of the Discord user. This alias will be expected to be the name of the tab in all related spreadsheets such as Esper Resonance.
* Column C: The administrator access column. For each user that you want to give admin rights to, enter the string "admin" into this column. Admins can add/remove espers, units, etc - basically full control of the sheet. Only give admin rights to people you trust!

**How it Works:**
At runtime, any attempt to perform a write operation is indirected through the access control spreadsheet. The originating discord user's snowflake ID is grabbed directly from the Discord server and used to look up the corresponding alias in the access control spreadsheet. That alias is then used to identify the name of the tab in the Esper Resonance (etc) spreadsheet, to which the discord user has permission to write. When a new member wants access, you need to grant it by adding their snowflake ID to the access control list and assign them an alias. To make them an admin, add "admin" in the third column.

For reads, a similar process is performed but it is non-authoritative, because reads are assumed to be safe for everyone. There is no *private* data in the spreadsheets, and the write-control is only implemented to prevent griefing.


## Extra Credit: OCR
There is experimental support for extracting data from screenshots. The initial support is for vision cards only, and just tries to extract the text from a file (when run standalone)
or from an image attachment (if uploaded to the channel). To make this work, you need...
* Google's OCR library, [tesseract-ocr](https://github.com/tesseract-ocr/tesseract)...
* ... and the [pytesseract](https://pypi.org/project/pytesseract/) library for interacting with it.
* [OpenCV](https://pypi.org/project/opencv-python/)
* [NumPy](https://numpy.org/) amd imutils.


## Running Integration Tests
The bot now includes basic integration tests that cover most (but not all) functionality, as a sanity check. Please be aware that the integration tests will make network calls to Google APIs. By default, Google limits traffic from any specific project to 100-requests-per-100-seconds. This isn't 100 *network calls*, but rather 100 *Google Sheets requests*, and the bot often sends multiple requests in a single network call. To reduce the danger of the integration tests causing the running bot to be throttled, the integration tests forcefully pause (with a countdown) after each major milestone in order to give time for the Google APIs to "cool down". This should keep the traffic well under the 100-requests-per-100-seconds limit.

First, set up the configuration file ```integration_test_config.json``` in the same directory as ```bot_config.json```. They look very similar, but the IDs of the Google spreadsheets that you specify here must be 
different than the IDs you specify in the ```bot_config.json```. This is super important so bears saying a second time: **The integration test spreadsheets MUST NOT BE THE SAME as the regular spreadsheets that you use in bot_config.json!** These sheets will be wiped every time you run the integration tests! You have been warned!
```
{
  "esper_resonance_spreadsheet_id": "your_integration_testing_google_spreadsheet_id_here",
  "sandbox_esper_resonance_spreadsheet_id": "your_integration_testing_google_spreadsheet_id_here",
  "vision_card_spreadsheet_id": "your_vision_card_google_spreadsheet_id_here",
  "access_control_spreadsheet_id": "your_integration_testing_google_spreadsheet_id_here"
  "data_dump_root_path": "integ_test_res/mock_data_dump"
}
```

To run the integration tests, use the following commands (or run the convenience script [run_integration_tests.sh](run_integration_tests.sh), which does the same thing):
```
python3 -m venv bot-env
source bot-env/bin/activate
python3 wotv_bot_integration_test.py <tests_to_run>
```
... where &lt;tests_to_run&gt; should be either:
* The word "all" (without quotes), to run all integration tests, or...
* The name of a specific integration test from the integration test suite to be run. (TODO: allow more than one test to run in this way)