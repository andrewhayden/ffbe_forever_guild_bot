# Commands
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

`!skills-by-name`
> Find units who have the specified skill name. Note that this only searches skill NAMES, not skill DESCRIPTIONS. To search skill descriptions, use !skills-by-desc.
<br> Example: *!skills-by-name killer blade*

`!skills-by-desc`
> Find units who have the specified skill description. Note that this only searches skill DESCRIPTIONS, not skill NAMES. To search skill names, use !skills-by-name.
<br> Example: *!skills-by-desc "bestows Man Eater"*

`!vc-set`
> Send this message with no other text, and attach a screenshot of a vision card. The bot will save your vision card stats. If it doesn't work, see *!vc-debug* below.

`!vc-debug`
> Send this message with no other text, and attach a screenshot of a vision card. Instead of saving your vision card stats, the bot will extract debugging images and respond with them as an attachment.

`!vc vision-card-name`
> Get **your own** stats for the named vision card.
<br> Example: *!vc Odin*

`!vc-ability ability-text`
> Find vision cards that **you own** that have abilities matching the specified text. See rules on matching below, matching against "ability-text" is done in the same was as it is for esper names, etc.

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