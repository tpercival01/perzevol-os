import sys
from groq_engine import get_ai_recommendation

def print_header():
    print("\n" + "=" * 60)
    print(" VCT DRAFT ANALYST V3.1 (LIVE DRAFT MODE)")
    print(" Commands:")
    print("   agent name  -> add locked agent, e.g. jett")
    print("   final       -> final recommendation from current team")
    print("   panic       -> emergency top 3 map picks")
    print("   undo        -> remove last added agent")
    print("   reset       -> restart draft")
    print("   exit        -> close program")
    print("=" * 60 + "\n")

def print_team(team_comp):
    if team_comp:
        print(f"\n[TEAM] {', '.join(team_comp)}")
    else:
        print("\n[TEAM] No agents locked yet.")

def print_recommendation(map_name, team_comp, label="LIVE RECOMMENDATION"):
    print("\n[*] ANALYSING CURRENT DRAFT...")
    response = get_ai_recommendation(map_name, team_comp)

    print("\n" + "=" * 60)
    print(f" {label}")
    print("=" * 60)
    print(response)
    print("=" * 60 + "\n")

def normalise_agent(agent_name):
    return agent_name.strip().title()

def draft_session(map_name):
    team_comp = []

    print(f"\n[MAP] {map_name.upper()}")
    print("[>] Start entering agents as teammates lock them.")
    print("[>] Type 'final' when you need to lock your pick.\n")

    while True:
        try:
            command = input("[draft] > ").strip()

            if not command:
                continue

            command_lower = command.lower()

            if command_lower == "exit":
                sys.exit(0)

            if command_lower == "reset":
                print("\n[!] Draft reset.\n")
                return

            if command_lower == "panic":
                print(f"\n[!] PANIC TRIGGERED FOR {map_name.upper()} [!]")
                print_recommendation(map_name, [], label="PANIC LOCK OPTIONS")
                continue

            if command_lower == "undo":
                if team_comp:
                    removed = team_comp.pop()
                    print(f"\n[-] Removed {removed}")
                else:
                    print("\n[!] No agents to remove.")
                print_team(team_comp)

                if team_comp:
                    print_recommendation(map_name, team_comp)
                continue

            if command_lower == "final":
                print_team(team_comp)
                print_recommendation(map_name, team_comp, label="FINAL LOCK RECOMMENDATION")
                continue

            agent = normalise_agent(command)

            if agent in team_comp:
                print(f"\n[!] {agent} is already listed.")
                continue

            team_comp.append(agent)
            print_team(team_comp)

            # Auto-suggest after every locked teammate.
            print_recommendation(map_name, team_comp)

        except KeyboardInterrupt:
            print("\n[!] System Terminated.")
            sys.exit(0)

def main_loop():
    print_header()

    while True:
        try:
            map_name = input("[?] Enter Map: ").strip()

            if not map_name:
                continue

            if map_name.lower() == "exit":
                break

            if map_name.lower() == "panic":
                print("\n[!] PANIC BUTTON HIT [!]")
                print(get_ai_recommendation("Unknown", [], is_panic=True))
                continue

            draft_session(map_name)

        except KeyboardInterrupt:
            print("\n[!] System Terminated.")
            sys.exit(0)

if __name__ == "__main__":
    main_loop()