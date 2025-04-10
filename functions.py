import requests
import json
from datetime import datetime, date, timedelta  
import calendar
import database
import schedulista_api
import pytz

TARGET_TZ = pytz.timezone('America/New_York')

def send_example(service,owner_id):
    info = database.get_dataset(owner_id)
    examples = info.get("examples")
    result = examples.get(str(service))
    if examples:
        return f'{service} example: {result}'
    return "example not found please check our feed"

def cancel_appointment(appointment_id):
    schedulista_api.cancel_appointment(appointment_id)

def reschedule_appointment(client_id,appointment_id,start_time,duration):
    start_time = start_time[:19]
    dt = datetime.fromisoformat(start_time)
    end_time = dt + timedelta(minutes=int(duration))
    end_time = end_time.strftime("%Y-%m-%dT%H:%M:%S")
    appointment = schedulista_api.reschedule(client_id,appointment_id,start_time,end_time,duration)

def book_appointment(_id,args,owner_id):
    name = args.get("name")
    phone_number = args.get("phone_number")
    service = args.get("service")
    deposit_amount = args.get("deposit_amount")
    deal_price = args.get("deal_price")
    start_time = args.get("booked_datetime")
    note = args.get("note")
    duration = args.get("duration","60")
    
    client = schedulista_api.get_clients(phone_number)
    if client:
        client = client[0][0]
        print(client)
        client_id = client.get("id")
    else:
        try:
            client = schedulista_api.create_client(name,phone_number)
            if client.get("errors"):
                raise client["errors"][0]
            client_id = client["id"]
        except Exception as error:
            try:
                client = schedulista_api.create_client(name,"")
                if client.get("errors"):
                    raise client["errors"][0]
                client_id = client["id"]
            except Exception as error:
                print(error)
                return "The phone number format is invalid please correct it and try again!"

    args["client_id"] = client_id
    # save into the database 
    # create an appointment
    start_time = start_time[:19]
    dt = datetime.fromisoformat(start_time)
    end_time = dt + timedelta(minutes=int(duration))
    end_time = end_time.strftime("%Y-%m-%dT%H:%M:%S")
    
    appointment = schedulista_api.create_appointment(
            client_id=client_id,
            name=name,
            phone_number=phone_number,
            start_time=start_time,
            end_time=str(end_time),
            duration=duration,
            note=note
        )
    appointment_id = appointment["created_appointment"]["id"]
    args["appointment_id"] = appointment_id
    database.set_appointment(_id,args,owner_id)
    return f"Appointment has been booked. Appointment ID: {appointment_id}"

def get_information(key, owner_id):
    info = database.get_dataset(owner_id)
    if info is None:
        return "data not found:"
    return info[key]

def get_next_weekday_date(weekday_name, reference_date=None):
    if reference_date is None:
        reference_date = datetime.now(tz=TARGET_TZ).date()

    weekday_name = weekday_name.lower()
    if len(weekday_name) == 3:
        for i, name in enumerate(calendar.day_abbr):
            if name.lower() == weekday_name:
                weekday_name = calendar.day_name[i].lower()
                break
        else:
            return None
    elif weekday_name not in [name.lower() for name in calendar.day_name]:
        return None

    try:
        target_weekday = [name.lower() for name in calendar.day_name].index(weekday_name)
        days_ahead = (target_weekday - reference_date.weekday() + 7) % 7
        if days_ahead == 0:
            days_ahead = 7

        next_date = reference_date + timedelta(days=days_ahead)  
        return next_date

    except ValueError:
        return None

def availablity(date_input):
    """
    Checks availability for a given date or weekday using the target timezone.
    Supports "today", "tomorrow", weekday names, "next [weekday]",
    and YYYY-MM-DD date formats.

    Args:
        date_input: The date or weekday to check.

    Returns:
        The availability data from the API, or an error message.
    """
    today_in_tz = datetime.now(tz=TARGET_TZ).date()
    general = False
    resolved_date = None

    date_input_lower = date_input.lower()

    if date_input_lower == "general":
        general = True
        resolved_date = today_in_tz
        date_input = "today"
    elif date_input_lower == "today":
        resolved_date = today_in_tz
    elif date_input_lower == "tomorrow":
        resolved_date = today_in_tz + timedelta(days=1)
    elif date_input_lower in [day.lower() for day in calendar.day_name] + [day.lower() for day in calendar.day_abbr]:
        resolved_date = get_next_weekday_date(date_input_lower, reference_date=today_in_tz)
    elif date_input_lower.startswith("next "):
        try:
            weekday = date_input_lower.split(" ")[1]
            resolved_date = get_next_weekday_date(weekday, reference_date=today_in_tz)
            if not resolved_date:
                return f"Invalid weekday provided after 'next': {weekday}"
        except IndexError:
            return "Please provide a day after 'next' keyword"
    else:
        try:
            resolved_date = datetime.strptime(date_input, "%Y-%m-%d").date()
        except ValueError:
            return "Invalid date format. Please use YYYY-MM-DD, 'today', 'tomorrow', or a weekday name (e.g., 'Monday', 'next Tuesday')."

    if not resolved_date:
        general = True
        resolved_date = today_in_tz

    formatted_date = resolved_date.strftime("%Y%m%d")

    time_zone_url_param = "Eastern+Time+(US+%26+Canada)"

    if general:
        first_of_month_date = resolved_date.replace(day=1)
        formatted_start_date = first_of_month_date.strftime("%Y%m%d")
        url = f"https://www.schedulista.com/schedule/bartaesthetics/available_days_json?preview_from=https%3A%2F%2Fwww.schedulista.com%2Fsettings&service_id=1074592366&start_date={formatted_start_date}&time_zone={time_zone_url_param}&scan_to_first_available=true"
    else:
        url = f"https://www.schedulista.com/schedule/bartaesthetics/available_times_json?preview_from=https%3A%2F%2Fwww.schedulista.com%2Fsettings&service_id=1074592411&date={formatted_date}&time_zone={time_zone_url_param}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        
        parsed_data = json.loads(response.text)

        processed = {
            "query_details": {
                "input": date_input,
                "resolved_date": resolved_date.strftime("%Y-%m-%d"),
                "resolved_day": resolved_date.strftime("%A"),
                "timezone": str(TARGET_TZ),
                "type": "general_days" if general else "specific_day_times"
            },
             "today": {
                "date": today_in_tz.strftime("%Y-%m-%d"),
                "day": today_in_tz.strftime("%A")
            }
        }

        if general:
            processed["available_days"] = []
            if "available_days" in parsed_data and isinstance(parsed_data["available_days"], dict):
                 processed["available_days"] = [
                    {
                        "date": datetime.strptime(d, "%Y%m%d").strftime("%Y-%m-%d"),
                        "day": datetime.strptime(d, "%Y%m%d").strftime("%A")
                    } for d in sorted(parsed_data["available_days"].keys())
                ]

            if parsed_data.get("first_available_day"):
                fad_date = datetime.strptime(parsed_data["first_available_day"], "%Y%m%d")
                processed["first_available_day"] = {
                    "date": fad_date.strftime("%Y-%m-%d"),
                    "day": fad_date.strftime("%A")
                }
            else:
                processed["first_available_day"] = None
        else:
            processed["available_times"] = []
            if isinstance(parsed_data, list):
                 for slot in parsed_data:
                    try:
                        start_dt_aware = datetime.fromisoformat(slot["start_time"])
                        start_dt_local = start_dt_aware.astimezone(TARGET_TZ)
                        formatted_time = start_dt_local.strftime("%I:%M %p %Z")
                        processed["available_times"].append({
                             "start_time_iso": slot["start_time"],
                             "start_time_formatted": formatted_time,
                        })
                    except (ValueError, KeyError):
                        processed["available_times"].append({
                            "error": "Could not parse time slot",
                            "raw_slot": slot
                        })

            else:
                processed["error"] = "Unexpected response format for available times."
                processed["raw_response"] = parsed_data

        return json.dumps(processed, indent=2)
        
    except requests.exceptions.RequestException as e:
        return json.dumps({"error": f"Error fetching availability: {e}", "url_requested": url}, indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Error decoding availability response from Schedulista.", "url_requested": url}, indent=2)
    except Exception as e:
        return json.dumps({"error": f"An unexpected error occurred: {e}", "url_requested": url}, indent=2)

def is_time_available(appointment_time, schedule):
    for slot in schedule.get("available_times"):
        slot_time = slot["start_time"][:19]  # Extract only the YYYY-MM-DDTHH:MM:SS part

        # Convert slot time to a common format
        formatted_slot_time = datetime.strptime(slot_time, "%Y-%m-%dT%H:%M:%S")

        try:
            if "T" in appointment_time:  # Handle ISO 8601 format
                formatted_appointment_time = datetime.strptime(appointment_time, "%Y-%m-%dT%H:%M:%S")
            else:
                formatted_appointment_time = datetime.strptime(appointment_time, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            formatted_appointment_time = datetime.strptime(appointment_time, "%Y-%m-%d %H:%M")  # Handle missing seconds

        if formatted_slot_time == formatted_appointment_time:
            return True

    return False

if __name__ == "__main__":
    print(send_example("classic",17841433182941465))
