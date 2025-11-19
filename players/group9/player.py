from __future__ import annotations

from typing import Any
import math
from math import ceil
from random import random

from core.action import Action, Move, Obtain
from core.message import Message
from core.player import Player
from core.snapshots import HelperSurroundingsSnapshot
from core.views.player_view import Kind
from core.animal import Gender
import core.constants as c


def distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x1 - x2, y1 - y2)


class Player9(Player):
    """
    Noah's Helpers (improved):

    - Territory-based exploration: Voronoi wedges around the Ark assigned
      deterministically by helper index/num_helpers.
    - Message encoding (1 byte) to report findings and collections.
    - Multi-phase behavior based on turns remaining until rain.
    - Dynamic priorities: rarity weighting and completion bonuses.
    - Conservative forced-return rules: empty helpers allowed more time.
    """

    FLOCK_CAPACITY = 4

    # Shared ark state (class-level for type checkers)
    shared_ark_animals: set[tuple[str, Gender]] = set()
    shared_ark_version: int = 0

    def __init__(
        self,
        id: int,
        ark_x: int,
        ark_y: int,
        kind: Kind,
        num_helpers: int,
        species_populations: dict[str, int],
    ):
        super().__init__(id, ark_x, ark_y, kind, num_helpers, species_populations)

        # Snapshot & state
        self.current_snapshot: HelperSurroundingsSnapshot | None = None
        self.position = (ark_x, ark_y)
        self.forced_return = False

        # Ark knowledge shared
        cls = type(self)
        if not hasattr(cls, "shared_ark_animals"):
            cls.shared_ark_animals = set()
            cls.shared_ark_version = 0
        self.ark_animals = set(cls.shared_ark_animals)
        self.local_ark_version = cls.shared_ark_version

        # Species ordering (rarity)
        self.rarity_order = sorted(species_populations.keys(), key=lambda s: species_populations.get(s, 0))
        self.rarity_map = {s: i for i, s in enumerate(self.rarity_order)}
        # small int mapping 1..31
        self.int_to_species = {i + 1: s for i, s in enumerate(self.rarity_order)}
        self.species_to_int = {s: i for i, s in self.int_to_species.items()}

        # helper fields
        self.sweep_angle = (2.0 * math.pi * (id % max(1, num_helpers))) / max(1, num_helpers)
        self.num_helpers = max(1, num_helpers)

        # role
        if self.kind == Kind.Noah:
            print("Noah online: coordinating helpers")
        else:
            print(f"Helper {self.id} initialized; wedge angle={self.sweep_angle:.2f}")

        # stuck detection
        self.last_cell = None
        self.last_flock_size = 0
        self.stuck_turns = 0

    # ---------------- Message encoding ----------------
    # Bits: [type:2][gender:1][species:5]
    # type: 0=found,1=collected,2=onark,3=need
    def _encode_msg(self, species: str | None, gender: Gender | None, mtype: int) -> int:
        if species is None:
            return 0
        sid = int(self.species_to_int.get(species, 0))
        if sid <= 0:
            return 0
        sid = sid & 0x1F
        g = 1 if (gender is not None and gender == Gender.Female) else 0
        b = ((mtype & 0x3) << 6) | ((g & 0x1) << 5) | sid
        return int(b)

    def _decode_msg(self, b: int) -> dict:
        b = int(b) & 0xFF
        if b == 0:
            return {"type": None}
        mtype = (b >> 6) & 0x3
        g = (b >> 5) & 0x1
        sid = b & 0x1F
        species = self.int_to_species.get(sid)
        gender = Gender.Female if g == 1 else Gender.Male
        return {"type": mtype, "species": species, "gender": gender}

    # ---------------- Ark sync ----------------
    def _sync_ark_information(self, snapshot: HelperSurroundingsSnapshot) -> None:
        cls = type(self)
        if snapshot.ark_view is not None:
            ark_animals = {(str(a.species_id), a.gender) for a in snapshot.ark_view.animals}
            cls.shared_ark_animals = set(ark_animals)
            cls.shared_ark_version = getattr(cls, "shared_ark_version", 0) + 1
            self.ark_animals = set(ark_animals)
            self.local_ark_version = cls.shared_ark_version
            return
        if getattr(cls, "shared_ark_version", 0) != self.local_ark_version:
            self.ark_animals = set(getattr(cls, "shared_ark_animals", set()))
            self.local_ark_version = getattr(cls, "shared_ark_version", 0)

    # ---------------- Utilities ----------------
    def _is_at_ark(self, snapshot: HelperSurroundingsSnapshot) -> bool:
        x, y = snapshot.position
        ax, ay = self.ark_position
        return int(x) == int(ax) and int(y) == int(ay)

    def _get_available_turns(self, snapshot: HelperSurroundingsSnapshot) -> int:
        if snapshot.is_raining and getattr(self, "rain_start_turn", None) is None:
            self.rain_start_turn = snapshot.time_elapsed
        if getattr(self, "rain_start_turn", None) is not None:
            turns_since = snapshot.time_elapsed - self.rain_start_turn
            return max(0, c.START_RAIN - turns_since)
        return max(0, c.MIN_T - snapshot.time_elapsed)

    def _find_rarest_needed_species(self) -> str | None:
        # return species name that still needs a pair
        for s in self.rarity_order:
            if not ((s, Gender.Male) in self.ark_animals and (s, Gender.Female) in self.ark_animals):
                return s
        return None

    def _species_needed_score(self, species: str) -> float:
        # lower population -> higher priority
        idx = self.rarity_map.get(species, len(self.rarity_order))
        return (len(self.rarity_order) - idx) + 1.0

    # Voronoi wedge owner: returns helper index owning that wedge
    def _owner_of_pos(self, x: float, y: float) -> int:
        dx = x - self.ark_position[0]
        dy = y - self.ark_position[1]
        ang = math.atan2(dy, dx)
        frac = (ang + math.pi) / (2 * math.pi)
        return int(frac * self.num_helpers) % self.num_helpers

    # ---------- Movement helpers ----------
    def _get_random_move(self) -> Action | None:
        ox, oy = self.position
        for _ in range(8):
            nx = ox + (random() - 0.5)
            ny = oy + (random() - 0.5)
            if (nx, ny) != (ox, oy) and self.can_move_to(nx, ny):
                return Move(nx, ny)
        ax, ay = self.move_towards(self.ark_position[0], self.ark_position[1])
        if (ax, ay) != (ox, oy) and self.can_move_to(ax, ay):
            return Move(ax, ay)
        return None

    def _get_safe_move_action(self, tx: float, ty: float) -> Action | None:
        nx, ny = self.move_towards(tx, ty)
        nx = max(0, min(c.X - 1, nx))
        ny = max(0, min(c.Y - 1, ny))
        if self.can_move_to(nx, ny):
            return Move(nx, ny)
        return self._get_random_move()

    def _move_to_ark(self) -> Action | None:
        return self._get_safe_move_action(self.ark_position[0], self.ark_position[1])

    def _move_to_cell(self, cx: int, cy: int) -> Action | None:
        return self._get_safe_move_action(cx + 0.5, cy + 0.5)

    # ---------- Target scoring / hunting ----------
    def _get_best_animal_on_cell(self, cellview: Any) -> Any | None:
        if not cellview or not getattr(cellview, "animals", None):
            return None
        # prefer needed species first (gender known only if same cell)
        for a in cellview.animals:
            if a.gender == Gender.Unknown:
                continue
            if (str(a.species_id), a.gender) in self.flock:
                continue
            s = str(a.species_id)
            has_pair = ((s, Gender.Male) in self.ark_animals) and ((s, Gender.Female) in self.ark_animals)
            if not has_pair:
                return a
        # otherwise any obtainable
        for a in cellview.animals:
            if a.gender == Gender.Unknown:
                continue
            if a in self.flock:
                continue
            return a
        return None

    def _find_best_animal_to_chase(self, snapshot: HelperSurroundingsSnapshot, avoid_sectors: set[int] | None = None) -> tuple[int, int] | None:
        avoid_sectors = avoid_sectors or set()
        best_score = float("inf")
        best_cell = None
        noah_target = self._find_rarest_needed_species()
        avail_turns = self._get_available_turns(snapshot)
        phase = 1 if avail_turns > 1000 else (2 if avail_turns > 300 else 3)

        for cellview in snapshot.sight:
            if not getattr(cellview, "animals", None):
                continue
            # skip ark cell
            if int(cellview.x) == int(self.ark_position[0]) and int(cellview.y) == int(self.ark_position[1]):
                continue

            cx = cellview.x + 0.5
            cy = cellview.y + 0.5
            dist = distance(self.position[0], self.position[1], cx, cy)
            owner = self._owner_of_pos(cx, cy)
            in_avoid = owner in avoid_sectors

            # base: distance weighted by phase (phase 3: time pressure -> stronger distance penalty)
            dist_weight = 1.0 + (phase - 1) * 1.5
            score = dist * dist_weight

            # species-based bonuses: prefer needed/completion
            best_species_priority = 0.0
            has_needed = False
            min_rarity_idx = len(self.rarity_order)
            for a in cellview.animals:
                sid = str(a.species_id)
                idx = self.rarity_map.get(sid, len(self.rarity_order))
                min_rarity_idx = min(min_rarity_idx, idx)
                # completion bonus if ark has one gender only
                has_m = (sid, Gender.Male) in self.ark_animals
                has_f = (sid, Gender.Female) in self.ark_animals
                if not (has_m and has_f):
                    has_needed = True
                    # rarer -> bigger bonus
                    best_species_priority = max(best_species_priority, (len(self.rarity_order) - idx) * 2.0)

            if has_needed:
                score -= 30.0 + best_species_priority
            elif noah_target and self.rarity_map.get(noah_target) == min_rarity_idx:
                score -= 12.0

            # avoid sectors claimed by others
            if in_avoid:
                score += 12.0

            # prefer cells in our wedge
            if owner == (self.id % self.num_helpers):
                score -= 4.0

            # minor bias for rarer species
            score -= max(0.0, (len(self.rarity_order) - min_rarity_idx) * 0.2)

            if score < best_score:
                best_score = score
                best_cell = (cellview.x, cellview.y)

        return best_cell

    # ---------- Main hooks ----------
    def check_surroundings(self, snapshot: HelperSurroundingsSnapshot) -> int:
        # set local snapshot/position
        self.current_snapshot = snapshot
        self.position = snapshot.position
        self.flock = set(snapshot.flock)
        self._sync_ark_information(snapshot)

        # Noah: broadcast rarest needed species as a "need" message
        if self.kind == Kind.Noah:
            target = self._find_rarest_needed_species()
            if target is not None:
                return self._encode_msg(target, None, 3)  # type=3 = need
            return 0

        # Helpers: decide what to broadcast
        # If we are on an animal cell and know a species/gender, broadcast FOUND
        cell = None
        cx, cy = int(self.position[0]), int(self.position[1])
        if snapshot.sight.cell_is_in_sight(cx, cy):
            try:
                cell = snapshot.sight.get_cellview_at(cx, cy)
            except Exception:
                cell = None

        if cell and getattr(cell, "animals", None):
            # report a best animal on cell if it's interesting
            best = self._get_best_animal_on_cell(cell)
            if best:
                species = str(best.species_id)
                gender = best.gender if best.gender != Gender.Unknown else None
                return self._encode_msg(species, gender, 0)  # found

        # otherwise broadcast our wedge id (non-zero)
        wedge = (self.id % self.num_helpers) + 1
        return wedge

    def get_action(self, messages: list[Message]) -> Action | None:
        if self.kind == Kind.Noah:
            return None

        snapshot = self.current_snapshot
        if snapshot is None:
            return None

        # update simple stuck tracking
        ax, ay = int(self.position[0]), int(self.position[1])
        flock_size = len(self.flock)
        if self.last_cell == (ax, ay) and self.last_flock_size == flock_size:
            self.stuck_turns += 1
        else:
            self.stuck_turns = 0
        self.last_cell = (ax, ay)
        self.last_flock_size = flock_size

        # decode messages
        occupied_wedges: set[int] = set()
        found_reports: list[dict] = []
        for msg in messages:
            # if message is from Noah, prefer decoding as encoded 'need'
            if msg.from_helper.kind == Kind.Noah:
                decoded = self._decode_msg(msg.contents)
                if decoded.get("type") == 3 and decoded.get("species") is not None:
                    # Noah says 'need' for species
                    self.noah_target = decoded.get("species")
                continue
            # helpers: content may be encoded byte or wedge id
            if msg.contents is None:
                continue
            if 0 < int(msg.contents) <= 255:
                decoded = self._decode_msg(int(msg.contents))
                if decoded.get("type") is not None:
                    found_reports.append(decoded)
                    continue
            # else treat as wedge id
            try:
                code = int(msg.contents)
                if code > 0:
                    occupied_wedges.add((code - 1) % self.num_helpers)
            except Exception:
                pass

        # compute forced_return conservatively
        # distance in turns
        dx = (self.position[0] - self.ark_position[0])
        dy = (self.position[1] - self.ark_position[1])
        turns_to_ark = ceil(math.hypot(dx, dy) / c.MAX_DISTANCE_KM)
        available = self._get_available_turns(snapshot)
        # if carrying animals, larger margin; if empty, allow more exploration
        margin = 10 if len(self.flock) > 0 else 3
        self.forced_return = turns_to_ark + margin > available

        at_ark = self._is_at_ark(snapshot)

        # AT ARK behavior
        if at_ark:
            # unload happens automatically; sync ark
            self._sync_ark_information(snapshot)
            # if not much time left, wait
            if self._get_available_turns(snapshot) <= 5:
                return None
            # else look for nearby targets greedily
            target = self._find_best_animal_to_chase(snapshot, avoid_sectors=occupied_wedges)
            if target:
                return self._move_to_cell(*target)
            return self._get_random_move()

        # NOT AT ARK
        # 1) Forced return overrides
        if self.forced_return:
            return self._move_to_ark()

        # 2) If we have flock and there are animals on our cell, try to obtain good ones
        cellview = None
        try:
            cx, cy = int(self.position[0]), int(self.position[1])
            if snapshot.sight.cell_is_in_sight(cx, cy):
                cellview = snapshot.sight.get_cellview_at(cx, cy)
        except Exception:
            cellview = None

        if flock_size > 0:
            # attempt greedy obtain on current cell if exists
            if cellview and getattr(cellview, "animals", None):
                best = self._get_best_animal_on_cell(cellview)
                if best:
                    return Obtain(best)
            # otherwise head towards the best nearby target if safe
            tgt = self._find_best_animal_to_chase(snapshot, avoid_sectors=occupied_wedges)
            if tgt:
                return self._move_to_cell(*tgt)
            # fallback: return to ark
            return self._move_to_ark()

        # 3) empty flock: try to obtain on current cell first
        if cellview and getattr(cellview, "animals", None):
            best = self._get_best_animal_on_cell(cellview)
            if best:
                return Obtain(best)

        # 4) hunt according to wedge ownership + reports
        target = self._find_best_animal_to_chase(snapshot, avoid_sectors=occupied_wedges)
        if target:
            return self._move_to_cell(*target)

        # 5) nothing visible: sweep according to assigned angle
        dx = math.cos(self.sweep_angle) * c.MAX_DISTANCE_KM * 0.9
        dy = math.sin(self.sweep_angle) * c.MAX_DISTANCE_KM * 0.9
        tx = max(0, min(c.X - 1, self.position[0] + dx))
        ty = max(0, min(c.Y - 1, self.position[1] + dy))
        return self._get_safe_move_action(tx, ty)
