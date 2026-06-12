OFFICE_INFO = {
    "name": "Smile Care Dental",
    "phone": "(410) 555-0100",
    "location": "123 Main Street, Annapolis MD 21401",
    "hours": {
        "monday": "8:00 AM - 6:00 PM",
        "tuesday": "8:00 AM - 6:00 PM",
        "wednesday": "8:00 AM - 6:00 PM",
        "thursday": "8:00 AM - 6:00 PM",
        "friday": "8:00 AM - 6:00 PM",
        "saturday": "9:00 AM - 2:00 PM",
        "sunday": "Closed",
    },
    "hours_summary": "Monday through Friday 8am to 6pm, Saturday 9am to 2pm, closed Sunday",
    "insurance": ["Delta Dental", "Cigna", "Aetna", "BlueCross BlueShield"],
    "services": ["Teeth Cleaning", "Teeth Whitening", "Fillings", "Emergency Care", "X-Rays", "Crowns", "Root Canals"],
    "open_slots": [
        "Tuesday at 2:00 PM",
        "Wednesday at 10:00 AM",
        "Thursday at 3:00 PM",
        "Friday at 11:00 AM",
        "Saturday at 9:00 AM",
    ],
}

FAQ_KNOWLEDGE = """
OFFICE INFORMATION:
- Name: Smile Care Dental
- Address: 123 Main Street, Annapolis MD 21401
- Phone: (410) 555-0100
- Hours: Monday-Friday 8am-6pm, Saturday 9am-2pm, Closed Sunday

SERVICES OFFERED:
- Routine teeth cleaning and checkups
- Professional teeth whitening
- Dental fillings for cavities
- Emergency dental care
- Dental X-rays
- Crowns and bridges
- Root canals

INSURANCE ACCEPTED:
- Delta Dental
- Cigna
- Aetna
- BlueCross BlueShield
- We also offer self-pay pricing plans

PRICING (approximate, varies by procedure):
- New patient exam + cleaning: $150-$200 without insurance
- Teeth whitening: $300-$500
- Fillings: $100-$300 depending on size
- Emergency exam: $75-$150

APPOINTMENT AVAILABILITY THIS WEEK:
- Tuesday at 2:00 PM
- Wednesday at 10:00 AM
- Thursday at 3:00 PM
- Friday at 11:00 AM
- Saturday at 9:00 AM

POLICIES:
- New patients welcome
- Please arrive 15 minutes early for first visit
- 24-hour cancellation notice required
- We send appointment reminders via text
"""


def get_available_slots() -> list[str]:
    return OFFICE_INFO["open_slots"]


def get_faq_context() -> str:
    return FAQ_KNOWLEDGE
