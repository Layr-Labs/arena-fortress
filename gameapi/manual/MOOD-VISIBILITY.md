# What a vanilla player sees of a strange mood's demands

Resolves the open item in docs/GAME-API.md ("mood item lists may be more than a vanilla player sees (audit d11)").

## Question

`observe.moods[]` reports, per moody citizen: `unit_id`, `mood`, `skill`, `job` (StrangeMood* job type),
`claimed_building_id`, `claimed_workshop`, and `items_needed[]` taken straight from the mood job's
`job_items.elements`: `item` (item type or "any"), `material` (exact mat_type/mat_index), `flags[]` (raw job_item
flags1-3 bits, e.g. silk/plant/yarn cloth, body part), `quantity`, `collected` (job items attached to that element)
and `available` (revealed, unclaimed items passing DFHack's isSuitableItem/isSuitableMaterial tests;
`available_approx` when the element has no item type). Which of these can a player of DF 53.x (Steam/premium UI,
vanilla, no DFHack) actually see?

## What vanilla shows

1. Announcements. The mood itself is announced with a mood-specific line ("is taken by a fey mood!", "withdraws from
   society...", "has been possessed!", "looses a roaring laughter, fell and terrible!", "begins to stalk and
   brood...") and the unit profile shows a matching line ("Has the aspect of one fey!" etc.); the unit's task reads
   "Strange Mood" [W53]. Claiming a workshop, starting work and the outcome each get their own announcement [ANN].
   Verified (wiki, v53.16-tagged). The exact wording of the claim announcement (in our recollection "<dwarf> has
   claimed a <workshop>.") is not quoted on these pages: uncertain.
2. Demands. When the moody dwarf is idle in the claimed workshop because it cannot find the next item, selecting
   the workshop shows a cycling series of clues, one per demanded item, in collection order: fey "I must have
   <demand>!", macabre "Yes. I need <demand>.", secretive "sketches pictures of <demand>", possessed "<artifact>
   needs <demand>..." [W53 Demands, DF14]. Steam players confirm this in the premium UI: "Wait for them to claim a
   workshop, then click on it. They will tell you what you need" [S5]; "i clicked it saying he needs stone....rock
   and cloth.... thread" [S1]; "The things that the dwarf needs are listed in order in which they will try to
   retrieve them" [S1]. Verified for the item category. The wiki says the clues appear only "while the dwarf is
   waiting inside it" (stated for secretive; the general Demands text ties them to the dwarf being idle) [W53]: the
   list is not shown while the dwarf is still successfully gathering, nor once everything is collected (then the
   workshop shows "works furiously!" etc.) [W53].
3. Material specificity depends on the mood. Fey text names the category precisely ("silk cloth", "raw green
   glass", "metal bars") and states a preferred metal outright; secretive and possessed clues are generic ("cloth...
   thread", "bars... metal"), and the player must infer the material from the dwarf's preferences [W53 Demands].
   A Steam reply: "When the strange mood is due to the dwarf being possessed, it doesn't show the specific type of
   cloth" [S1]. Verified; exact fey wording for a metal not quoted.
4. Quantities. Each clue is shown for about 2 seconds per required item, so a clue lasting 6 seconds means 3 items,
   "however, the mood's primary material will always be shown for only 2 seconds, even if more than one is required"
   [W53 Demands]. A Steam player saw a "repeating loop of wool cloth, silk cloth x4 wool cloth" [S4]. So
   quantities are visible (by timing or repetition) except for the primary material. Verified as wiki text, with
   one player report; the timing detail is not independently confirmed for v53.
5. Collected so far. Items brought in are listed in the workshop's contents as tasked for the job ("In the workshop
   are 15+ bolts of silk listed as to be used for the artifact" [S4]; DF2014 "seen as 'tasked' when looking at the
   workshop" [W53 Secretive]). Since gathering is in order, the player can tell which demand is next [W53]. Verified.
   The per-element attribution is player inference, not a displayed number.
6. Claimed workshop: visible (announcement, the workshop becomes unusable and shows the dwarf's messages) [W53, ANN].
7. Available counts: nothing in vanilla displays them. A player could count stocks (stocks screen), but only against
   what they know of the demand; for secretive/possessed moods they do not know the exact material or cloth type.
8. Rationale check: DFHack tags `showmood` ("Shows all items needed for the active strange mood") as `armok`,
   defined as "tools which give the player god-like powers or the ability to access information the game
   intentionally keeps hidden" [DFH, DFHT].

## Field-by-field

| Field | Vanilla | Note |
|---|---|---|
| unit_id, mood | visible | announcement and profile line name the mood type |
| skill | partially | implied by the claimed workshop and the dwarf's skills; DF does not print the mood skill |
| job (StrangeMood*) | partially | task shows "Strange Mood"; the subtype is implied by the workshop |
| claimed_building_id, claimed_workshop | visible | announcement; the workshop itself |
| items_needed[].item | partially | only while the dwarf waits in the workshop; as a demand category ("rock", "cloth", "bones") |
| items_needed[].material | partially / hidden | fey: preferred metal and cloth type are stated; secretive/possessed: generic only; exact mat_index of other materials never shown |
| items_needed[].flags | hidden | raw job_item bits; their effect (silk vs plant vs yarn cloth, body part) is only what the fey text says |
| items_needed[].quantity | partially | inferable from clue timing/repetition, not for the primary material |
| items_needed[].collected | visible (derived) | workshop contents show the tasked items; per-element mapping is inference |
| items_needed[].available | derived, leaks | computed with the exact hidden spec; for non-fey moods it tells the agent which material is wanted |

## Conclusion

Expose partially. `unit_id`, `mood`, `claimed_building_id`, `claimed_workshop`, `job` and `skill` can stay (the last
two are harmless shorthand for what the workshop implies). `items_needed` as it stands is `showmood`: it is shown
from the moment the mood starts, with exact materials, raw flags and full quantities, and `available` hands the agent
the answer to "which material does a secretive dwarf want". That is more than a vanilla player sees.

## Proposed change (for gameapi/facts; not applied)

In the `moods` block of `gameapi/facts/lua/observe.lua`:

1. Gate the list on waiting. Emit `items_needed` only when the mood dwarf is waiting: the unit stands inside the
   claimed building's extents (x1..x2, y1..y2, z) and the job is not fetching (`not (j.flags.fetching or
   j.flags.bringing)`; flag names to be checked against df.job_flags in 53.x). Otherwise emit `waiting = false` and no
   list. Add `waiting = true|false` to the entry. Keep `collected_items` (count of `j.items`) always, since the
   workshop contents are always visible.
2. Replace the per-element spec with a vanilla demand. Each element becomes `{demand, quantity, collected}`:
   `demand` is the wiki demand category derived from item_type and flags (boulder -> "rock", blocks -> "blocks",
   wood -> "wood", bar -> "metal bars", smallgem -> "cut gems", rough -> "rough gems", rough glass -> "raw glass",
   bones -> "bones", shell -> "shells", leather -> "leather", cloth -> "cloth", corpse/body part -> "body parts").
   Only for `mood == 'Fey'` add the precise form the fey text states: `material` for metal bars and glass (the mat
   string), and `cloth` = silk|plant|yarn from the flags. Drop `flags` and the exact `material` otherwise.
3. Quantity: report `quantity` for every element except the first (the primary material, element 0), where it is
   null, matching "the primary material will always be shown for only 2 seconds".
4. Drop `available` and `available_approx`. If a stock hint is wanted, compute it against the visible demand only
   (category, plus fey material/cloth type), name it `available_visible_spec`, and keep the approx marker; a player
   could get the same count from the stocks screen.
5. Update docs/GAME-API.md section 5 (Moods) and close the "audit d11" open item, citing this note; bump the obs
   schema since field names change.

Uncertain points worth an in-game check (scenarios/lua/mood.lua already strikes moods): whether fey demands are also
shown while the dwarf is still gathering, the exact claim-announcement text, and the 2-second timing rule in v53.

## Sources

- [W53] Strange mood (main namespace, tagged v53.16): https://dwarffortresswiki.org/index.php/Strange_mood
  (sections Types of moods, Demands, Caveats). Fetched 2026-10-23.
- [DF14] DF2014:Strange mood: https://dwarffortresswiki.org/index.php/DF2014:Strange_mood (same rules, "Press q and
  highlight the workshop to receive a series of clues").
- [ANN] Announcement: https://dwarffortresswiki.org/index.php/Announcement
- [S1] Steam, "dwarf strange mood" (Dec 2022): https://steamcommunity.com/app/975370/discussions/0/3716062978744373442/
- [S4] Steam, "strange mood bug?" (Dec 2022): https://steamcommunity.com/app/975370/discussions/0/3727324132815876570/
- [S5] Steam, "strange mood" (Jan 2023): https://steamcommunity.com/app/975370/discussions/0/3727324132827287918/
- [S6] Steam, "Strange Mood Questions" (Jan 2023, "He's ranting: Cloth.... thread.... Metal.... bars.... Bones...yes..."):
  https://steamcommunity.com/app/975370/discussions/0/5828254465008502780/
- [DFH] DFHack showmood: https://docs.dfhack.org/en/stable/docs/tools/showmood.html
- [DFHT] DFHack tags (armok): https://docs.dfhack.org/en/stable/docs/Tags.html

Reddit and Bay 12 could not be fetched (blocked / rate-limited); the Steam threads are from the premium UI era
(v50.x), not specifically 53.x.
