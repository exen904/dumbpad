try:
    from typing import Optional, Tuple
except ImportError:
    pass
from micropython import const

import kmk.handlers.stock as handlers
from kmk.keys import Key, make_key
from kmk.kmk_keyboard import KMKKeyboard
from kmk.modules import Module


class _ComboState:
    RESET = const(0)
    MATCHING = const(1)
    ACTIVE = const(2)
    IDLE = const(3)


class Combo:
    fast_reset = False
    per_key_timeout = False
    timeout = 50
    _remaining = []
    _timeout = None
    _state = _ComboState.IDLE

    def __init__(
        self,
        match: Tuple[Key, ...],
        result: Key,
        fast_reset=None,
        per_key_timeout=None,
        timeout=None,
    ):
        '''
        match: tuple of keys (KC.A, KC.B)
        result: key KC.C
        '''
        self.match = match
        self.result = result
        if fast_reset is not None:
            self.fast_reset = fast_reset
        if per_key_timeout is not None:
            self.per_key_timeout = per_key_timeout
        if timeout is not None:
            self.timeout = timeout

    def __repr__(self):
        return f'{self.__class__.__name__}({[k.code for k in self.match]})'

    def matches(self, key):
        raise NotImplementedError

    def reset(self):
        self._remaining = list(self.match)


class Chord(Combo):
    def matches(self, key):
        if key in self._remaining:
            self._remaining.remove(key)
            return True
        else:
            return False


class Sequence(Combo):
    fast_reset = True
    per_key_timeout = True
    timeout = 1000

    def matches(self, key):
        if self._remaining and self._remaining[0] == key:
            self._remaining.pop(0)
            return True
        else:
            return False


class Combos(Module):
    def __init__(self, combos=[]):
        self.combos = combos
        self._key_buffer = []

        make_key(
            names=('LEADER', 'LDR'),
            on_press=handlers.passthrough,
            on_release=handlers.passthrough,
        )

    def during_bootup(self, keyboard):
        self.reset(keyboard)

    def before_matrix_scan(self, keyboard):
        return

    def after_matrix_scan(self, keyboard):
        return

    def before_hid_send(self, keyboard):
        return

    def after_hid_send(self, keyboard):
        return

    def on_powersave_enable(self, keyboard):
        return

    def on_powersave_disable(self, keyboard):
        return

    def process_key(self, keyboard, key: Key, is_pressed, int_coord):
        if is_pressed:
            return self.on_press(keyboard, key, int_coord)
        else:
            return self.on_release(keyboard, key, int_coord)

    def on_press(self, keyboard: KMKKeyboard, key: Key, int_coord: Optional[int]):
        # refill potential matches from timed-out matches
        if self.count_matching() == 0:
            for combo in self.combos:
                if combo._state == _ComboState.RESET:
                    combo._state = _ComboState.MATCHING

        # filter potential matches
        for combo in self.combos:
            if combo._state != _ComboState.MATCHING:
                continue
            if combo.matches(key):
                continue
            combo._state = _ComboState.IDLE
            if combo._timeout:
                keyboard.cancel_timeout(combo._timeout)
            combo._timeout = keyboard.set_timeout(
                combo.timeout, lambda c=combo: self.reset_combo(keyboard, c)
            )

        match_count = self.count_matching()

        if match_count:
            # At least one combo matches current key: append key to buffer.
            self._key_buffer.append((int_coord, key, True))
            key = None

            for first_match in self.combos:
                if first_match._state == _ComboState.MATCHING:
                    break

            # Single match left: don't wait on timeout to activate
            if match_count == 1 and not any(first_match._remaining):
                combo = first_match
                self.activate(keyboard, combo)
                if combo._timeout:
                    keyboard.cancel_timeout(combo._timeout)
                    combo._timeout = None
                self._key_buffer = []
                self.reset(keyboard)

            # Start or reset individual combo timeouts.
            for combo in self.combos:
                if combo._state != _ComboState.MATCHING:
                    continue
                if combo._timeout:
                    if combo.per_key_timeout:
                        keyboard.cancel_timeout(combo._timeout)
                    else:
                        continue
                combo._timeout = keyboard.set_timeout(
                    combo.timeout, lambda c=combo: self.on_timeout(keyboard, c)
                )
        else:
            # There's no matching combo: send and reset key buffer
            self.send_key_buffer(keyboard)
            self._key_buffer = []
            if int_coord is not None:
                key = keyboard._find_key_in_map(int_coord)

        return key

    def on_release(self, keyboard: KMKKeyboard, key: Key, int_coord: Optional[int]):
        for combo in self.combos:
            if combo._state != _ComboState.ACTIVE:
                continue
            if key in combo.match:
                # Deactivate combo if it matches current key.
                self.deactivate(keyboard, combo)

                if combo.fast_reset:
                    self.reset_combo(keyboard, combo)
                    self._key_buffer = []
                else:
                    combo._remaining.insert(0, key)
                    combo._state = _ComboState.MATCHING

                key = combo.result
                break

        else:
            # Non-active but matching combos can either activate on key release
            # if they're the only match, or "un-match" the released key but stay
            # matching if they're a repeatable combo.
            for combo in self.combos:
                if combo._state != _ComboState.MATCHING:
                    continue
                if key not in combo.match:
                    continue

                # Combo matches, but first key released before timeout.
                elif not any(combo._remaining) and self.count_matching() == 1:
                    keyboard.cancel_timeout(combo._timeout)
                    self.activate(keyboard, combo)
                    self._key_buffer = []
                    keyboard._send_hid()
                    self.deactivate(keyboard, combo)
                    if combo.fast_reset:
                        self.reset_combo(keyboard, combo)
                    else:
                        combo._remaining.insert(0, key)
                        combo._state = _ComboState.MATCHING
                    self.reset(keyboard)

                elif not any(combo._remaining):
                    continue

                # Skip combos that allow tapping.
                elif combo.fast_reset:
                    continue

                # This was the last key released of a repeatable combo.
                elif len(combo._remaining) == len(combo.match) - 1:
                    self.reset_combo(keyboard, combo)
                    if not self.count_matching():
                        self.send_key_buffer(keyboard)
                        self._key_buffer = []

                # Anything between first and last key released.
                else:
                    combo._remaining.insert(0, key)

            # Don't propagate key-release events for keys that have been
            # buffered. Append release events only if corresponding press is in
            # buffer.
            pressed = self._key_buffer.count((int_coord, key, True))
            released = self._key_buffer.count((int_coord, key, False))
            if (pressed - released) > 0:
                self._key_buffer.append((int_coord, key, False))
                key = None

        # Reset on non-combo key up
        if not self.count_matching():
            self.reset(keyboard)

        return key

    def on_timeout(self, keyboard, combo):
        # If combo reaches timeout and has no remaining keys, activate it;
        # else, drop it from the match list.
        combo._timeout = None

        if not any(combo._remaining):
            self.activate(keyboard, combo)
            # check if the last buffered key event was a 'release'
            if not self._key_buffer[-1][2]:
                keyboard._send_hid()
                self.deactivate(keyboard, combo)
            self._key_buffer = []
            self.reset(keyboard)
        else:
            if self.count_matching() == 1:
                # This was the last pending combo: flush key buffer.
                self.send_key_buffer(keyboard)
                self._key_buffer = []
            self.reset_combo(keyboard, combo)

    def send_key_buffer(self, keyboard):
        for (int_coord, key, is_pressed) in self._key_buffer:
            new_key = None
            if not is_pressed:
                try:
                    new_key = keyboard._coordkeys_pressed[int_coord]
                except KeyError:
                    new_key = None
            if new_key is None:
                new_key = keyboard._find_key_in_map(int_coord)

            keyboard.resume_process_key(self, new_key, is_pressed, int_coord)
            keyboard._send_hid()

    def activate(self, keyboard, combo):
        combo.result.on_press(keyboard)
        combo._state = _ComboState.ACTIVE

    def deactivate(self, keyboard, combo):
        combo.result.on_release(keyboard)
        combo._state = _ComboState.IDLE

    def reset_combo(self, keyboard, combo):
        combo.reset()
        if combo._timeout is not None:
            keyboard.cancel_timeout(combo._timeout)
            combo._timeout = None
        combo._state = _ComboState.RESET

    def reset(self, keyboard):
        for combo in self.combos:
            if combo._state != _ComboState.ACTIVE:
                self.reset_combo(keyboard, combo)

    def count_matching(self):
        match_count = 0
        for combo in self.combos:
            if combo._state == _ComboState.MATCHING:
                match_count += 1
        return match_count
