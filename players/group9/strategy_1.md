# How Our Player9 Helper Logic Works (Simple Explanation)

This version of **Player9** is designed to make helpers act like efficient, greedy collectors who keep moving and grab animals quickly

## 1. Noah’s Job
Noah does **one thing**:

- **Broadcast the rarest needed species** so helpers know what to focus on.

---

## 2. Helpers’ Job
Each helper acts independently but follows the same priority rules.

### **Priority 1: Stay Safe**
Helpers immediately return to the Ark if:
- It starts **raining**
- Their **inventory is full** (capacity = 4 animals)

This prevents helpers from dying with animals in their inventory.

## 3. Grabbing Animals (Greedy Behavior)
Helpers try to **grab any animals they can** on the cell they’re standing on:

1. If there are animals under their feet:
   - They **take Noah’s target species first**
   - Otherwise, they grab **any animal available**
   - They stay on the cell and keep grabbing until full or empty


## 4. Chasing Animals
If there are no animals on their current cell:

- Helpers look at everything in their **sight radius**
- They move toward:
  1. The **closest target species** (Noah’s broadcast)
  2. Otherwise, the **closest animal of any kind**

This makes helpers actively hunt instead of wandering randomly.

## 5. Sweeping the Map
If helpers can’t see any animals at all:

- They **sweep across the map** in straight lines determined by a unique angle per helper
- They **bounce off walls** to avoid getting stuck
- If a move is illegal, they use a **random move fallback** to stay active

This ensures they keep exploring and don’t freeze in empty areas.

---

Noah encodes gender preference into its 1-byte broadcast:
Base species code remains in the low 7 bits.
Top bit (0x80) set => prefer Female. No top bit => prefer Male.
Noah sets the top bit when the ark already contains a Male for that species (so Noah requests a Female).
Helpers decode Noah's message and set:
self.noah_target_species (species letter)
self.noah_prefer_gender ('F' or 'M')
Helpers now use noah_prefer_gender:
_get_best_animal_on_cell: when on a cell with Noah's target species, prefer an animal matching preferred gender; fallback to any animal of that species.
_find_best_animal_to_chase: prefer cells that contain the preferred gender (those cells are prioritized).
