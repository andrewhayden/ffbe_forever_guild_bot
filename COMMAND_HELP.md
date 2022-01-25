# Commands
`!astrologize/!divine/!foretell/!predict <question>`
> Ask the bot a question, and see what it says!
<br> Example *!predict Will I pull the latest time-limited unit?*
<br> Example *!astrologize Will we be victorious?*
<br> Example *!divine What books room should we run?*
<br> Example *!foretell How many days till UR Learte?*

`!daily-reminders <reminders>`
> Set up daily reminders. This is best done in a private message channel to avoid spamming the room. Currently the only supported daily reminder is about double drop rates (see !mats command, below, for context). The reminder will fire within 10 minutes after daily reset, with some randomness to prevent abuse/spam/throttling. Examples:
<br> To see if you currently have daily reminders set: *!daily-reminders*
<br> To set up a daily reminder about double-drop rate rooms: *!daily-reminders mats*
<br> To stop receiving daily reminders: *!daily-reminders none*

`!leaderboard-set category-name score [proof URL]`
> BETA FUNCTIONALITY - MAY NOT BE 100% FUNCTIONAL
> <br>Set your own score for the given category, optionally providing a proof URL (e.g. a link to a screenshot or video proving your score). Can be abbreviated as just "!leader", and you only have to type the first few characters of the category - enough to unambiguously match one specific ranked category. The category name is not case-sensitive. Finally, the score you specify must be a simple integer - no decimal points, commas etc... just digits 0-9. Examples:
<br> Set your score for "Max-Chain" to 16 hits, without proof: *!leaderboard-set Max-Chain 16*
<br> If there's no other category that starts with "max", you can also do: *!leaderboard-set max 16"
<br> And to set your "high score" to 9999 with a link to a video proving your supremacy, succinctly: *!leader-set high 9999 https://www.youtube.com/watch?v=dQw4w9WgXcQ*

`!mats`
> Prints today's double drop rate room as well as tomorrow's.

`!resonance unit-name/esper-name`
> Get **your own** resonance for the named unit and esper.
<br> Example: *!resonance mont/cactuar*

`!resonance unit-or-esper-name`
> Get a full listing of **your own** resonances for the named unit *or* esper. This will generate a listing, in the same order as the spreadsheet, of all the resonance data for the specified unit *or* esper.
<br> Example: *!resonance lamia*

`!resonance-set unit-name/esper-name level[/priority[/comment]]`
> Set **your own** resonance for the named unit and esper to the specified level. Optionally, include a priority at the end (H/High/M/Medium/L/Low). If a priority has already been set, it will be preserved. If no priority has been set, the default is "Low". Finally, you can add a comment like "for evade build" as the final string, or the string "<blank>" (without the quotes) to clear an existing comment.
<br> Example: *!resonance-set mont/cactuar 9/m/because everyone loves cactuars*

`!resonance-lookup discord-nickname unit-name/esper-name`
> Get **someone else's** resonance for the named unit and esper. Unlike !resonance and !resonance-set, the discord-nickname here is not resolved against the user's snowflake ID. Put another way, it's just the name of the tab in the spreadsheet. This can access data of a former guild members, if your guild leader hasn't deleted it.
<br> Example: *!resonance-lookup JohnDoe mont/cactuar*

`!roll <dice>`
> Roll some dice. The syntax is the number of dice, the letter 'd', and the number of sides on each die. Maximum 50 dice at once, to prevent abuse (and because that's a lot of dice for the bot to keep track of...) Examples:
<br> To roll 3 6-sided dice: *!roll 3d6*
<br> To roll 2 9-sided dice: *!roll 2d9*
<br> To roll 17 19-sided dice: *!roll 17d19*

`!schedule`
> Prints the weekly rotation of double drop rate rooms, etc.

`!skills-by-name`
> Deprecated. Use `!unit-search skill-name [search_text]` instead.

`!skills-by-desc`
> Deprecated. Use `!unit-search skill-desc [search_text]` instead.

`!unit-search`
> Flexible, powerful search command to search all units with various filters. Examples are best to explain this, so consider jumping to the table below for those helpful examples and then reading the full rules below.
> <br><br>The unit-search command makes use multiple lines to refine results, with each line discarding any units/skills/etc that don't match the constraints. The rules are as follows: 
> * The first line always starts with `!unit-search`
> * `!unit-search` is either followed by the word `all` (meaning, list all units that match) or one of the following **refinement criteria**:
>   * For a **unit search**, showing only the unit that matches:
>     * `rarity [UR|MR|SR|R|N]` matches only units that have the specified rarity.
>     * `element [earth|wind|fire|water|ice|lightning|dark|light|none]` matches only units that have the specified element. Multi-element units like Sakura are returned if any of their elements match.
>   * For a **skill search**, showing the skill, the unit, and the job and level that the skill is learned at:
>     * `skill-name [search_text]` matches only units that have a skill whose name matches the specified search text. Enclose the `search_text` in double-quotes to match only the full `search_text` string, otherwise a fuzzy match is performed using all the words in `search_text`.
>     * `skill-desc [search_text]` or `skill-description [search_text]` is exactly like `skill-name` except that the search is performed in the *description* of the skill, not the name.
>   * For a **job search**, showing the job and the unit that matches:
>     * `job [search_text]` or `job-name [search_text]` matches only units that have a job whose name matches the specified search text.  Enclose the `search_text` in double-quotes to match only the full `search_text` string, otherwise a fuzzy match is performed using all the words in `search_text`.
> * Each additional line can contain any of the **refinement criteria** listed above, **one per line**.
> * As each line is processed, **only units that match everything** are kept. Each line discards all units that fail to match.
> * Any line (*except* the `!unit-search` line itself) can start with the word 'not' to flip the meaning of the refinement. For example, the meaning of `job Knight` (match only units that have the "Knight" job) can be reversed as `not job Knight` (match only units that *do not* have the "Knight" job).
> * The type of the first search refinement (the words following `!unit-search`) determines how the results are formatted (a unit listing, a skill listing, a job listing, etc).
> * Results are always sorted alphabetically in ascending order by unit name. This can give rise to some strangeness with units whose names start with non-letters, like "Whisper" (whose in-game name actually includes the quotations).

| Command Example                                                                     | Meaning                                                                                                |
|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| Line 1: `!unit-search rarity UR`<br>Line 2: `element Earth `                        | List all UR units with Earth element.                                                                  |
| Line 1: `!unit-search skill-name Killer`<br>Line 2: `rarity MR`                     | List all skills whose name contains "Killer", from only MR units.                                      |
| Line 1: `!unit-search skill-desc "Man Eater"`<br>Line 2: `job Lord`                 | List all skills whose description contains the exact phrase "Man Eater", from units with the job Lord. |
| Line 1: `!unit-search element Light`<br>Line 2: `job Paladin`                       | List all units with Light element and the Paladin job.                                                 |
| Line 1: `!unit-search all`<br>Line 2: `not element earth`<br>Line 3: `not job lord` | List all units who have neither the earth element nor the Lord job.                        |

`!vc-set`
> Send this message with no other text, and attach a screenshot of a vision card. The bot will save your vision card stats. If it doesn't work, see *!vc-debug* below.

`!vc-debug`
> Send this message with no other text, and attach a screenshot of a vision card. Instead of saving your vision card stats, the bot will extract debugging images and respond with them as an attachment.

`!vc vision-card-name`
> Get **your own** stats for the named vision card.
<br> Example: *!vc Odin*

`!vc-ability ability-text`
> Find vision cards that **you own** that have abilities matching the specified text. See rules on matching below, matching against "ability-text" is done in the same was as it is for esper names, etc.

`!whimsy`
> Set up personal reminders for Whimsy Shops. You'll receive a first reminder when NRG starts counting towards the shop spawning again, and a second reminder once the shop can actually spawn again. If you already have a reminder set, this tells you the status of that reminder (functions the same as "!whimsy when" (see below)). To forcibly restart the existing reminder, use "!whimsy set-reminder".

`!whimsy cancel`
> Cancel and any all outstanding personal whimsy shop reminders.

`!whimsy set-reminder`
> Same as "!whimsy" but forcibly restarts the existing timer, if one already exists.

`!whimsy when`
> Ask when your next Whimsy-related event is, based on the last time you use !whimsy. Tells you how about how long it will be before NRG spending counts or, if that time has already passed, tells you about how long it will be before the shop can spawn again. Accurate to the nearest minute, rounded down.

# Additional Notes
## Searching within names of Espers, Units, Vision Cards, Skills, etc

You don't have to type out "Sterne Leonis" and "Tetra Sylphid"; you can just shorthand it as "stern/tetra", or even "st/te". Specifically, here's how searching works:
1. If you enclose the name of the unit, esper, vision card (etc) in double quotes, only an **EXACT MATCH** will be performed. This is handy to force the correct unit when dealing with some unique situations like "Little Leela" and "Little Leela (Halloween)"
    - Note: When searching skill descriptions and skill names, the exact match can appear anywhere in the skill name or description. For other searches, the entire name/description/etc must match the search text.
2. Otherwise, if there's only one possible name that **STARTS WITH** the shorthand, that's enough. For example, there's only one unit whose name starts with "Lass" (Lasswell), so you can just type "Lass" (without the quotes).

3. Otherwise, if there's only one possible name that **HAS ALL THE WORDS YOU ENTERED**, that's enough. For example, there's only one unit whose name contains both "Lee" and "Hallow", it's "Little Leela (Halloween)". So this is enough to identify her.

4. Otherwise, an error will be returned - either because (1) there was no exact match or, in the case of (2) and (3) above there were multiple possible matches and you need to be more specific.

 ## Shorthand & Convenience
* You can abbreviate "resonance" as just "res" in all the resonance commands.