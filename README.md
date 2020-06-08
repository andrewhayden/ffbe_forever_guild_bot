# ffbe_forever_guild_bot
A bot for the War of the Visions guild, FFBEForever

Helpful Links:
* https://discord.com/developers/applications
* https://discordpy.readthedocs.io/en/latest/intro.html

Steps to prep your environment to work on or run this bot:
* sudo apt-get update
* sudo apt-get install python3-distutils
* curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
* sudo python3 get-pip.py
* python3 -m pip install -U discord.py
* sudo apt-get install python3-venv

After checkout, and whenever you want to run the bot:
* python3 -m venv bot-env
* source bot-env/bin/activate

Now configure the bot to connect to discord:
* Visit https://discordpy.readthedocs.io/en/latest/discord.html and follow instructions to create your bot on Discord
* Create a file called bot_config.json in the checkout directory. Add the following JSON bindings:
  * "discord_bot_token": "&lt;your discord bot token&gt;"
* Back in the Discord console, generate your invite link. Make sure to give the following permissions in the invite URL:
  * Send Messages
  * Embed Links
  * Read Message History (future expansion)
  * Add Reactions (future expansion)
  * The permissions above can be abbreviated in the URL as 84032.
* Use the invitation link to invite the bot to a server that you have the authority to add it to.
  * It's probably best to make your own private server first and test everything out.

Now configure the bot to connect to Google
* Visit https://developers.google.com/sheets/api/quickstart/python and follow instructions to create an OAuth app.
* When prompted how to configure, choose "Desktop Application"
* Download the credentials file and place it in the checkout directory. Rename it to google_credentials.json
* In your python virtual environemt:
  * pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
* Open the bot_config.json you created earlier and set the Google spreadsheet you want the bot to manage, as well as the ID of a sandbox for trying out potentially-problematic commands like adding espers and units:
  * "esper_resonance_spreadsheet_id": "&lt;your google spreadsheet ID&gt;"
  * "sandbox_esper_resonance_spreadsheet_id": "&lt;your google spreadsheet ID&gt;"
* Also add the ID of the administrative spreadsheet where you will bind Discord Snowflake IDs to guild aliases (used as tab names in the Resonance spreadsheet), and where you can set admin rights:
  * "access_control_spreadsheet_id": "&lt;your google spreadsheet ID&gt;"

You're ready to start now. Start the bot:
* In your python virtual environemt:
  * python3 ffbe_forever_guild_bot.py
* You will be prompted to visit a URL to authorize the bot for the first time. Do so.

That's it! The bot should be up and running now.

## The Access Control spreadsheet

This spreadsheet gates write access to writes, ensuring that a user can only modify their own data. Use the bot's hidden commands !whois <username> and !whoami to get the snowflake IDs. Populate three columns:
* Column A: Snowflake ID. Put the raw snowflake IDs in this column.
* Column B: Alias. For each Snowflake ID, put the alias of the Discord user. This alias will be expected to be the name of the tab in all related spreadsheets such as Esper Resonance.
* Column C: The administrator access column. For each user that you want to give admin rights to, enter the string "admin" into this column. Admins can add/remove espers, units, etc - basically full control of the sheet. Only give admin rights to people you trust!

**How it Works:**
At runtime, any attempt to perform a write operation is indirected through the access control spreadsheet. The originating discord user's snowflake ID is grabbed directly from the Discord server and used to look up the corresponding alias in the access control spreadsheet. That alias is then used to identify the name of the tab in the Esper Resonance (etc) spreadsheet, to which the discord user has permission to write. When a new member wants access, you need to grant it by adding their snowflake ID to the access control list and assign them an alias. To make them an admin, add "admin" in the third column.

For reads, a similar process is performed but it is non-authoritative, because reads are assumed to be safe for everyone. There is no *private* data in the spreadsheets, and the write-control is only implemented to prevent griefing.
