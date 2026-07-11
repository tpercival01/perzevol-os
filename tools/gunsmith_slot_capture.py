from __future__ import annotations

import argparse
import csv
import re
import time
from datetime import datetime
from pathlib import Path

import mss
import mss.tools
import pyautogui
from pynput import keyboard


pyautogui.PAUSE = 0.04
pyautogui.FAILSAFE = True


def slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def capture_monitor(monitor_index: int, output_path: Path) -> None:
    with mss.mss() as sct:
        monitors = sct.monitors

        if monitor_index >= len(monitors):
            raise ValueError(
                f"Monitor {monitor_index} not found. Available monitors: 1 to {len(monitors) - 1}"
            )

        shot = sct.grab(monitors[monitor_index])
        mss.tools.to_png(shot.rgb, shot.size, output=str(output_path))


def append_manifest(manifest_path: Path, row: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    exists = manifest_path.exists()

    with manifest_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "weapon",
                "slot",
                "index",
                "capture_type",
                "screenshot_path",
            ],
        )

        if not exists:
            writer.writeheader()

        writer.writerow(row)


def countdown(seconds: int = 3) -> None:
    for remaining in range(seconds, 0, -1):
        print(f"Starting in {remaining}...")
        time.sleep(1)


class GunsmithCaptureSession:
    def __init__(self, args: argparse.Namespace):
        self.weapon = args.weapon
        self.slot = args.slot
        self.count = args.count
        self.visible = args.visible
        self.monitor = args.monitor
        self.output = args.output
        self.settle = args.settle
        self.scroll_amount = args.scroll

        self.first_x: int | None = None
        self.first_y: int | None = None
        self.row_gap: int | None = None

        self.manual_index = 1
        self.stop_requested = False

    @property
    def output_dir(self) -> Path:
        return Path(self.output) / slug(self.weapon) / slug(self.slot)

    @property
    def manifest_path(self) -> Path:
        return Path(self.output) / "manifest.csv"

    def print_status(self) -> None:
        print("")
        print("Current session")
        print("---------------")
        print(f"Weapon:       {self.weapon}")
        print(f"Slot:         {self.slot}")
        print(f"Count:        {self.count}")
        print(f"Visible rows: {self.visible}")
        print(f"Monitor:      {self.monitor}")
        print(f"Scroll:       {self.scroll_amount}")
        print(f"First row:    {self.first_x}, {self.first_y}")
        print(f"Row gap:      {self.row_gap}")
        print("")

    def save_screenshot(self, index: int | None, capture_type: str) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

        # Base weapon screenshot goes in the weapon root:
        # captures/carbon_57/carbon_57__base__timestamp.png
        if capture_type == "base":
            output_dir = Path(self.output) / slug(self.weapon)
            filename = f"{slug(self.weapon)}__base__{timestamp}.png"

        # Attachment screenshots still go in the slot folder:
        # captures/carbon_57/barrel/carbon_57__barrel__001__timestamp.png
        else:
            output_dir = self.output_dir

            if index is None:
                filename = f"{slug(self.weapon)}__{capture_type}__{timestamp}.png"
            else:
                filename = (
                    f"{slug(self.weapon)}__{slug(self.slot)}__"
                    f"{str(index).zfill(3)}__{timestamp}.png"
                )

        output_dir.mkdir(parents=True, exist_ok=True)

        path = output_dir / filename
        capture_monitor(self.monitor, path)

        append_manifest(
            self.manifest_path,
            {
                "timestamp": timestamp,
                "weapon": self.weapon,
                "slot": "" if capture_type == "base" else self.slot,
                "index": "" if index is None else index,
                "capture_type": capture_type,
                "screenshot_path": str(path),
            },
        )

        print(f"Captured: {path}")

    def set_first_row(self) -> None:
        input("Move mouse over the FIRST visible attachment row, then press Enter here...")
        x, y = pyautogui.position()
        self.first_x = x
        self.first_y = y
        print(f"First row set: x={x}, y={y}")

    def set_second_row(self) -> None:
        if self.first_y is None:
            print("Set the first row first.")
            return

        input("Move mouse over the SECOND visible attachment row, then press Enter here...")
        x, y = pyautogui.position()
        self.row_gap = y - self.first_y
        print(f"Second row set: x={x}, y={y}")
        print(f"Row gap set to: {self.row_gap}px")

    def row_position(self, visible_row_index: int) -> tuple[int, int]:
        if self.first_x is None or self.first_y is None or self.row_gap is None:
            raise RuntimeError("Set first row and second row before sweeping.")

        x = self.first_x
        y = self.first_y + visible_row_index * self.row_gap
        return int(x), int(y)

    def capture_base(self) -> None:
        print("Make sure the base weapon stat screen is visible.")
        countdown()
        self.save_screenshot(None, "base")

    def manual_capture(self) -> None:
        print("Hover the attachment you want to capture.")
        countdown()
        self.save_screenshot(self.manual_index, "manual")
        self.manual_index += 1

    def sweep_slot(self) -> None:
        if self.first_x is None or self.first_y is None or self.row_gap is None:
            print("Set first row and second row before sweeping.")
            return

        self.stop_requested = False

        print("")
        print("Sweep starting.")
        print("F12 = emergency stop")
        print("Top-left mouse corner = PyAutoGUI failsafe")
        print("")
        print("Click/focus the game window during the countdown.")
        countdown()

        current_index = 1

        try:
            # First pass: capture all currently visible rows.
            first_page_rows = min(self.visible, self.count)

            for visible_row in range(first_page_rows):
                if self.stop_requested:
                    print("Sweep stopped by F12.")
                    return

                x, y = self.row_position(visible_row)

                # Nudge by 1px so the game definitely refreshes the right-hand stat panel.
                pyautogui.moveTo(x, y, duration=0.08)
                time.sleep(0.08)
                pyautogui.moveRel(1, 0, duration=0.03)
                time.sleep(0.08)
                pyautogui.moveRel(-1, 0, duration=0.03)

                time.sleep(self.settle)

                self.save_screenshot(current_index, "attachment")
                current_index += 1

            # Scrolling pass:
            # BO7's list overlaps after scrolling, so each scroll usually reveals
            # the next new attachment at the BOTTOM of the visible list.
            bottom_row_index = self.visible - 1

            while current_index <= self.count:
                if self.stop_requested:
                    print("Sweep stopped by F12.")
                    return

                print(f"Scrolling down for attachment {current_index}...")
                pyautogui.scroll(self.scroll_amount)
                time.sleep(0.75)

                x, y = self.row_position(bottom_row_index)

                # Move to the row, then nudge 1px to force BO7 to refresh the hover stat panel.
                pyautogui.moveTo(x, y, duration=0.08)
                time.sleep(0.08)
                pyautogui.moveRel(1, 0, duration=0.03)
                time.sleep(0.08)
                pyautogui.moveRel(-1, 0, duration=0.03)

                time.sleep(self.settle)

                self.save_screenshot(current_index, "attachment")
                current_index += 1

            print("Sweep complete.")

        except pyautogui.FailSafeException:
            print("Stopped by PyAutoGUI failsafe.")

        except KeyboardInterrupt:
            print("Stopped by Ctrl+C.")

        except Exception as exc:
            print(f"ERROR during sweep: {exc}")

    def change_weapon(self) -> None:
        new_weapon = input(f"Weapon [{self.weapon}]: ").strip()
        if new_weapon:
            self.weapon = new_weapon

        self.manual_index = 1
        self.first_x = None
        self.first_y = None
        self.row_gap = None

        print("Weapon changed. Recalibrate first and second rows.")


    def change_slot(self) -> None:
        new_slot = input(f"Slot [{self.slot}]: ").strip()
        if new_slot:
            self.slot = new_slot

        new_count = input(f"Attachment count [{self.count}]: ").strip()
        if new_count:
            self.count = int(new_count)

        new_visible = input(f"Visible rows [{self.visible}]: ").strip()
        if new_visible:
            self.visible = int(new_visible)

        self.manual_index = 1
        self.first_x = None
        self.first_y = None
        self.row_gap = None

        print("Slot changed. Recalibrate first and second rows.")

        def request_stop(self) -> None:
            self.stop_requested = True


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--weapon", required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--visible", type=int, required=True)
    parser.add_argument("--monitor", type=int, default=1)

    parser.add_argument("--output", default="captures")
    parser.add_argument("--settle", type=float, default=0.35)
    parser.add_argument("--scroll", type=int, default=-4)

    args = parser.parse_args()
    session = GunsmithCaptureSession(args)

    def on_press(key):
        if key == keyboard.Key.f12:
            session.request_stop()
            print("F12 pressed. Stop requested.")

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()

    while True:
        try:
            session.print_status()

            print("Menu")
            print("----")
            print("1  Set first visible attachment row")
            print("2  Set second visible attachment row")
            print("3  Capture base/current screen")
            print("4  Sweep current slot")
            print("5  Manual capture hovered attachment")
            print("6  Change slot/count/visible rows")
            print("7  Change weapon")
            print("q  Quit")
            print("")

            choice = input("Choose: ").strip().lower()

            if choice == "1":
                session.set_first_row()

            elif choice == "2":
                session.set_second_row()

            elif choice == "3":
                session.capture_base()

            elif choice == "4":
                session.sweep_slot()

            elif choice == "5":
                session.manual_capture()

            elif choice == "6":
                session.change_slot()

            elif choice == "7":
                session.change_weapon()

            elif choice == "q":
                print("Exiting.")
                break

            else:
                print("Unknown option.")

        except KeyboardInterrupt:
            print("")
            print("Ctrl+C received. Exiting.")
            break

        except Exception as exc:
            print(f"ERROR: {exc}")


if __name__ == "__main__":
    main()