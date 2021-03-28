Contains a mock data set meant for integration testing. Units in the data set:

* Mont (Earth MR):
  * Jobs: Lord, Paladin, Knight
  * Skills: Killer Blade, Master Ability, and Sentinel (to overlap with Engelbert, from Paladin job)
* Engelbert (Light UR):
  * Jobs: Paladin, Knight, Monk
  * Skill: Sentinel, from the Paladin job (to overlap with Mont)
* Tidus (Water UR) - missing some data, but hash fixups
  * Test cases (triggered by the problems with the data dump on release of FFX, which was missing most localizations for Tidus)
    * Missing localized unit name for unit ID UN_FF10_P_TIDU in en/UnitName.json
    * Missing localized job name for primary job JB_FF10_TIDU in en/JobName.json
    * Missing localized skill names and descriptions for basically all of Tidus' skills.
    * Missing critical data is supplemented by the non-testing file ../fixups.json
  * Jobs: Abes' Star Player, Paladin, Samurai
  * Has EX board
  * Has extra job levels that come with EX awakening: `{"ccsets": [{ "m": "JB_FF10_TIDU_M" }]`
* Yuna (Light UR) - missing some data, but WITHOUT fixups
  * Test cases (triggered by the problems with the data dump on release of FFX, which was missing most localizations for Tidus)
    * Missing localized unit name for unit ID UN_FF10_P_YUNA in en/UnitName.json
    * Missing localized job name for primary job JB_FF10_YUNA in en/JobName.json
    * Missing localized skill names and descriptions for basically all of Tidus' skills.
    * Missing critical data IS NOT supplemented by the non-testing file ../fixups.json (expect to survive gracefully anyhow)
  * Jobs: Summoner of Spira, Green Mage, Kotodama Wielder
  * Has EX board
  * Has extra job levels that come with EX awakening: `{"ccsets": [{ "m": "JB_FF10_YUNA_M" }]`
