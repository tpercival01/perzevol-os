import sys
from groq_engine import get_ai_recommendation

def print_header():
    print("\n" + "="*50)
    print(" VCT DRAFT ANALYST V3 (AI DRIVEN)")
    print(" Type 'PANIC' at any prompt for emergency lock-ins.")
    print(" Type 'EXIT' to close the program.")
    print("="*50 + "\n")

def main_loop():
    print_header()
    
    while True:
        try:
            # Step 1: Get Map
            map_name = input("[?] Enter Map: ").strip()
            if map_name.upper() == "EXIT":
                break
            if map_name.upper() == "PANIC":
                print("\n[!] PANIC BUTTON HIT [!]")
                print(get_ai_recommendation("Unknown", [], is_panic=True))
                continue
                
            # Step 2: Get Team Comp
            print("[?] Enter locked agents separated by commas (e.g. Jett, Omen)")
            comp_input = input("[?] Team: ").strip()
            
            if comp_input.upper() == "EXIT":
                break
            if comp_input.upper() == "PANIC":
                print(f"\n[!] PANIC TRIGGERED FOR {map_name.upper()} [!]")
                print(get_ai_recommendation(map_name, [], is_panic=True))
                continue
                
            team_comp = [
                agent.strip() for agent in comp_input.split(',') if agent.strip()
            ]
            
            # Step 3: Call AI
            print("\n[*] TRANSMITTING DATA TO LLAMA-3-70B...")
            response = get_ai_recommendation(map_name, team_comp)
            
            print("\n" + "="*50)
            print(" SYSTEM RECOMMENDATION")
            print("="*50)
            print(response)
            print("="*50 + "\n")
            
        except KeyboardInterrupt:
            print("\n[!] System Terminated.")
            sys.exit(0)

if __name__ == "__main__":
    main_loop()