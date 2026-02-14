import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
from services.toolkit_bridge import toolkit

def normalize(s):
    if not s: return ""
    return str(s).lower().replace(" ", "").replace("_", "").replace("-", "")

def verify_resolution():
    print("--- Verifying Alias Resolution Fix ---")
    if not toolkit.is_available():
        print("Toolkit NOT available")
        return

    problem_sites = [
        "Blachford", 
        "BAE Fylde", 
        "Sofina Haverhill", 
        "Parfetts - Birmingham",
        "Merry Hill"
    ]
    
    all_plants = toolkit.get_plants()
    print(f"Total Plants Loaded: {len(all_plants)}\n")
    
    for sh_site in problem_sites:
        print(f"Resolving '{sh_site}'...")
        plant_uid = None
        
        # 1. Direct
        p = toolkit.get_plant(sh_site)
        if p:
            plant_uid = p.get('plant_uid') or p.get('uid')
            if plant_uid:
                print(f"  -> Found via direct lookup: {plant_uid}")
        
        # 2. Fallback
        if not plant_uid:
            target_norm = normalize(sh_site)
            for p in all_plants:
                # Check Alias
                if normalize(p.get('alias')) == target_norm:
                    plant_uid = p.get('plant_uid') or p.get('uid')
                    print(f"  -> Found via Alias match ('{p.get('alias')}'): {plant_uid}")
                    break
                # Check Weather ID
                if normalize(p.get('weather_id')) == target_norm:
                    plant_uid = p.get('plant_uid') or p.get('uid')
                    print(f"  -> Found via Weather ID match ('{p.get('weather_id')}'): {plant_uid}")
                    break
        
        if not plant_uid:
            print("  -> FAILED to resolve")

if __name__ == "__main__":
    verify_resolution()
