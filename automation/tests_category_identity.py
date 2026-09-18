import sys
sys.path.insert(0, "/home/ianmcwherter/golden-home-project/automation")
from category_identity import in_category

CASES = [
    # (title, category, expected)
    ("Etekcity Digital Body Weight Bathroom Scale", "Seasonal Décor", False),
    ("Hargiis Non Slip Bathtub Mat", "Seasonal Décor", False),
    ("Amazon Basics Fast Drying Cotton Washcloths for Bathroom", "Seasonal Décor", False),
    ("Yarra-Decor Bedside Table Lamp with USB Ports", "Seasonal Décor", False),
    ("1000 sqft Spider Webs Halloween Decorations with 30 Fake Spiders", "Seasonal Décor", True),
    ("AerWo Halloween Decoration Black Lace Spiderweb Fireplace Mantle Scarf", "Seasonal Décor", True),
    ("Sattiyrch 15 inch Wreath Hanger for Front Door", "Seasonal Décor", True),
    ("Battery Operated LED String Lights for Christmas Tree", "Seasonal Décor", True),
    # regressions: the categories that were already working
    ("IRIS USA 6-Pack 54 Quart Storage Bins with Lids", "Home Storage", True),
    ("Owala FreeSip Stainless Steel Water Bottle 24 oz", "Home Storage", False),
    ("NICETOWN Blackout Curtains for Bedroom Thermal Insulated", "Window Treatments", True),
    ("Fenmzee Bedside Table Lamp for Bedroom", "Window Treatments", False),
    ("Utopia Towels 24 Pack Cotton Washcloths", "Bath Linens", True),
    ("Amazon Basics Slim Velvet Non-Slip Clothes Hangers", "Home", True),
    ("TERRO Liquid Ant Killer Bait Stations", "Home", False),
]
bad = 0
for title, cat, want in CASES:
    got = in_category(title, cat)
    ok = got == want
    if not ok: bad += 1
    print(f"  {'OK ' if ok else 'FAIL'} {str(got):<5} (want {want!s:<5}) [{cat}] {title[:52]}")
print(f"\n{bad} failure(s)")
