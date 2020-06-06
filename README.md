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
** "discord_bot_token": "<your discord bot token>"
* Back in the Discord console, generate your invite link. Make sure to give the following permissions in the invite URL:
** Send Messages
** Embed Links
** Read Message History (future expansion)
** Add Reactions (future expansion)
** The permissions above can be abbreviated in the URL as 84032.
* Use the invitation link to invite the bot to a server that you have the authority to add it to.
** It's probably best to make your own private server first and test everything out.

Now configure the bot to connect to Google
* Visit https://developers.google.com/sheets/api/quickstart/python and follow instructions to create an OAuth app.
* When prompted how to configure, choose "Desktop Application"
* Download the credentials file and place it in the checkout directory. Rename it to google_credentials.json
* In your python virtual environemt:
** pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
* Open the bot_config.json you created earlier and set the Google spreadsheet you want the bot to manage:
** "esper_resonance_spreadsheet_id": "<your google spreadsheet ID>"

You're ready to start now. Start the bot:
* In your python virtual environemt:
** python3 ffbe_forever_guild_bot.py
* You will be prompted to visit a URL to authorize the bot for the first time. Do so.

That's it! The bot should be up and running now.