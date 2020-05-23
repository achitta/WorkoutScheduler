from __future__ import print_function
import datetime
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import json
import time

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar']

def authorization():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    return creds

def get_calendar_ids(service: object) -> list:
    # Get Calendar Id for all specified calendars
    calendar_ids = []
    page_token = None
    while True:
        # Make API call 
        calendar_list = service.calendarList().list(pageToken=page_token).execute()
        print(calendar_list)
        # For each entry returned by API call, append the id to the 'calendar_ids'
        # if that calendar was included by user
        for calendar_list_entry in calendar_list['items']:
            if 'primary' in calendar_list_entry and calendar_list_entry['primary']:
                calendar_ids.append(calendar_list_entry['id'])
                continue
            else:
                flag = None
                while flag != 'Yes' and flag != 'No':
                    flag = input('Do you want to include {}? Enter Yes or No: '.format(calendar_list_entry['summary']))
                if flag == 'Yes':
                    calendar_ids.append(calendar_list_entry['id'])
        page_token = calendar_list.get('nextPageToken')
        if not page_token:
            break
    return calendar_ids

    #     for calendar_list_entry in calendar_list['items']:
    #         if calendar_list_entry['summary'] in calendars or ('primary' in calendar_list_entry and calendar_list_entry['primary']):
    #             calendar_ids.append(calendar_list_entry['id'])
    #     page_token = calendar_list.get('nextPageToken')
    #     if not page_token:
    #         break
    # print(calendar_ids)
def get_timezone_hour_offset() -> float:
    hours = time.timezone/3600
    if time.localtime( ).tm_isdst == 1.0:
        hours -= 1
    return hours

def get_monday_utc() -> object:
    # Get UTC of next Monday (if today is Monday use today) and the following Monday
    # These will serve as the bounds for the API call to get the events
    offset = get_timezone_hour_offset()
    suffix = 'T0{}:'.format(int(offset))
    if int(offset * 2) % 2 == 1:
        suffix += '30:00Z'
    else:
        suffix += '00:00Z'

    today = datetime.date.today()
    next_monday = today + datetime.timedelta(days=-today.weekday(), weeks=1)
    if today.weekday() == 0:
        next_monday = today

    next_next_monday = next_monday + datetime.timedelta(days=7)

    utc_monday = next_monday.isoformat() + suffix
    utc_monday_next = next_next_monday.isoformat() + suffix
    return utc_monday, utc_monday_next, next_monday

def get_weekly_event_list(service : object) -> list:
    # 2011-06-03T10:00:00-07:00
    # UTC time is 4 hours ahead of EST

    # Get necessary calendar ids 
    calendar_ids = get_calendar_ids(service)
    # print(calendar_ids)

    # Get UTC times for upcoming and following Monday 
    utc_monday, utc_monday_next, next_monday = get_monday_utc()

    result = []
    # For each calendar id
    for c_id in calendar_ids:
        page_token = None
        while True:
            # Make api call to get all events between upcoming and the following Monday
            events = service.events().list(calendarId=c_id, pageToken=page_token, timeMin=utc_monday, 
                                            timeMax = utc_monday_next, singleEvents = True, 
                                            orderBy='startTime').execute()

            # Store the start and ending times for each event along with their dates
            for event in events['items']:
                start = datetime.datetime.fromisoformat(event['start']['dateTime'])
                end = datetime.datetime.fromisoformat(event['end']['dateTime'])
                obj = {}
                obj['start'] = start.hour * 60 + start.minute
                obj['end'] = end.hour * 60 + end.minute
                obj['date'] = None
                if start.date().isoformat() == end.date().isoformat():
                    obj['date'] = start.date().isoformat()

                result.append(obj)

            page_token = events.get('nextPageToken')
            if not page_token:
                break

    # print(result)
    return result, next_monday

def sort_events_by_day(first_day: datetime.date, all_events : list) -> dict:
    result = {}
    for i in range(7):
        result[(first_day + datetime.timedelta(days=i)).isoformat()] = []
        # print((first_day + datetime.timedelta(days=i)).isoformat())

    for event in all_events:
        # print(event['date'])
        result[event['date']].append(event)
    # print(result)
    for date in result:
        # sorted(lis, key = lambda i: i['age']) 
        result[date] = sorted(result[date], key = lambda i: i['start'])
    return result

def apply_constraints(events: dict, other_constraints: list = []) -> dict:
    # NEED A FUNCTION TO SANITIZE USER INPUT and give dict of format {'start': start_time in mins, 'end': end time in mins}

    # For each constraint (dinner, sleep, etc.)
    for obj in other_constraints:
        start_time = obj['start']
        end_time = obj['end']
        # Apply to each date in events
        for date in events:
            flag = False
            temp = {'start': start_time, 'end': end_time, 'date': date}
            # obj['date'] = date
            # Search for where to insert constraint 
            for i, event in enumerate(events[date]):
                if start_time <= event['start']:
                    events[date].insert(i, temp)
                    flag = True
                    break
            if not flag:
                events[date].append(temp)
    
    print(events)
    print()
    events = merge_function(events)
    print(events)
    print()
    return events

def merge_function(events):
    result = {}
    for date in events:
        result[date] = []
        i = 1
        result[date].append(events[date][0])
        while i < len(events[date]):
            start = result[date][-1]['start']
            end = result[date][-1]['end']
            curr_start = events[date][i]['start']
            curr_end = events[date][i]['end']
            #If overlap, merge
            if (curr_start >= start and curr_start <= end) or (curr_end >= start and curr_end <= end):
                result[date][-1]['end'] = max(end, curr_end)
            else:
                result[date].append(events[date][i])
            i+=1 
    return result

def find_free_time(events: dict, exerciseLength : int = 90) -> dict:
    result = {}
    for date, ev_list in events.items():
        if date not in result:
            result[date] = []
        i = 0
        while i < len(ev_list) - 1:
            # if ev_list[i]['end'] < ev_list[i+1]['start']:
            if ev_list[i+1]['start'] - ev_list[i]['end'] > exerciseLength:
                obj = {'start': ev_list[i]['end'], 'end': ev_list[i+1]['start'], 'date': date}
                result[date].append(obj)
            i += 1
    # print()
    # print(result)
    # print()
    return result

def get_finalized_times(first_day: datetime.date, freeTimes : dict, workoutPlan : dict, 
                        flexible : bool = True, exLength : int = 90) -> dict :
    on_days = {}
    off_days = {}
    for i in range(7):
        if i in workoutPlan:
            on_days[i] = True
        else:
            off_days[i] = True
    
    result = {}
    missed = []
    for day_offset in workoutPlan:
        date = (first_day  + datetime.timedelta(days=day_offset)).isoformat()
        if len(freeTimes[date]) > 0:
            # result[date] = freeTimes[date][0]
            result[date] = {'time': {'start': freeTimes[date][0]['start'], 
                                    'end': freeTimes[date][0]['start'] + exLength}, 'summary': workoutPlan[day_offset]}
        else:
            missed.append(day_offset)
    if flexible:
        for day_offset in missed:
            if len(off_days) > 0:
                date = (first_day  + datetime.timedelta(days=list(off_days.keys())[0])).isoformat()

                if len(freeTimes[date]) > 0:
                    result[date] = {'time': freeTimes[date][0], 'summary': workoutPlan[day_offset]}

                off_days.pop(list(off_days.keys())[0])
    # print(result)
    return result

def schedule(service, finalized_times, attendees = []):
    for date in finalized_times:
        start_utc, end_utc = eastern_to_utc(finalized_times[date]['time']['start'], finalized_times[date]['time']['end'], date)
        event = {
            'summary': finalized_times[date]['summary'],
            'location': 'Gym',
            'description': '** Insert workouts here **',
            'start': {
                'dateTime': start_utc
            },
            'end': {
                'dateTime': end_utc
            },
            'attendees': attendees, 
            'reminders': {
                'useDefault': False,
                'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
                ],
            },
        }
        event = service.events().insert(calendarId='primary', body=event).execute()

def eastern_to_utc(start, end, date) -> object :
    date = datetime.datetime.fromisoformat(date)
    start_hour = start // 60
    start_minute = start % 60
    end_hour = end // 60
    end_minute = end % 60
    start_dt = (datetime.datetime(date.year, date.month, date.day, start_hour, start_minute) + datetime.timedelta(seconds=14400)).isoformat() + 'Z'
    end_dt = (datetime.datetime(date.year, date.month, date.day, end_hour, end_minute) + datetime.timedelta(seconds=14400)).isoformat() + 'Z'
    # print(start_dt)
    # print(end_dt)
    return start_dt, end_dt

def get_user_calendars():
    calendars = {}
    user_input = input('Do you want to use other calendars in addition to your primary? (Yes/No): ')
    if user_input == 'Yes':
        print('Enter \'DONE\' when you are calendar names:')
        while True:
            calendar = input('Calendar Names: ')
            if calendar == 'DONE':
                break
            calendars[(calendar.strip())] = True
    # print(calendars)   
    return calendars

def get_user_constraints():
    before = input('What is the earliest you are willing to work out? (Military Time): ')
    after = input('What is the latest you are willing to work out? (Military Time): ')
    print(before, after)
    result = []
    before = before.split(':')
    after = after.split(':')
    before_time = int(before[0]) * 60 + int(before[1])
    after_time = int(after[0]) * 60 + int(after[1])
    result.append({'start': 0, 'end': before_time})
    result.append({'start': after_time, 'end': 1439})
    # print(result)
    return result

def get_user_attendees():
    guests = []
    user_input = input('Do you have guests? (Yes/No): ')
    if user_input == 'Yes':
        print('Enter \'DONE\' when you are finished listing your guests\' emails:')
        while True:
            email = input('Guest Email: ')
            if email == 'DONE':
                break
            guests.append({'email': email})
    # print(guests)   
    return guests

def get_user_flexibility():
    flag = input('If you are too busy on a day, do you want to move that workout to an off day? (Yes/No): ')
    if flag == 'Yes':
        return True

    return False

def get_user_exercise_length():
    exLength = input('How long are your workouts in minutes?: ')
    return int(exLength)

def get_user_workout_plan():
    result = {}
    monday = input('What do you work out on Monday? If off day, enter OFF: ')
    if monday != 'OFF':
        result[0] = monday.strip()
    
    tuesday = input('What do you work out on Tuesday? If off day, enter OFF: ')
    if tuesday != 'OFF':
        result[1] = tuesday.strip()

    wednesday = input('What do you work out on Wednesday? If off day, enter OFF: ')
    if wednesday != 'OFF':
        result[2] = wednesday.strip()

    thursday = input('What do you work out on Thursday? If off day, enter OFF: ')
    if thursday != 'OFF':
        result[3] = thursday.strip()

    friday = input('What do you work out on Friday? If off day, enter OFF: ')
    if friday != 'OFF':
        result[4] = friday.strip()

    saturday = input('What do you work out on Saturday? If off day, enter OFF: ')
    if saturday != 'OFF':
        result[5] = saturday.strip()

    sunday = input('What do you work out on Sunday? If off day, enter OFF: ')
    if sunday != 'OFF':
        result[6] = sunday.strip()
    
    # print(result)
    return result

def get_user_information() -> dict:
    result = {}
    # result['calendars'] = get_user_calendars()
    # print()
    result['constraints'] = get_user_constraints()
    print()
    result['exerciseLength'] = get_user_exercise_length()
    print()
    result['workoutPlan'] = get_user_workout_plan()
    print()
    result['flexible'] = get_user_flexibility()
    print()
    result['attendees'] = get_user_attendees()
    print()
    print("Scheduling...")
    print()
    return result


def main():
    print('Workout Scheduler... Powered by Aditya Chitta')
    print()

    creds = authorization()

    print()

    info = get_user_information()
    print(info)
    service = build('calendar', 'v3', credentials=creds)
    print("reached 1")

    all_events, next_monday = get_weekly_event_list(service)
    print(all_events)
    print(next_monday)
    print("reached 2")

    events_sorted = sort_events_by_day(next_monday, all_events)
    print(events_sorted)
    print("reached 3")

    events_more = apply_constraints(events_sorted, info['constraints'])
    print(events_more)
    print("reached 4")

    free_times = find_free_time(events_more, info['exerciseLength'])
    print(free_times)
    print("reached 5")

    final_times = get_finalized_times(next_monday, free_times, info['workoutPlan'], info['flexible'], info['exerciseLength'])
    print(final_times)
    print("reached 6")
    
    schedule(service, final_times, info['attendees'])

    print('Done!')

    # all_events = [{'start': 1080, 'end': 1140, 'date': '2020-05-26'}, {'start': 630, 'end': 1080, 'date': '2020-05-27'}, {'start': 660, 'end': 1170, 'date': '2020-05-25'}, {'start': 630, 'end': 960, 'date': '2020-05-26'}, {'start': 540, 'end': 600, 'date': '2020-05-27'}, {'start': 600, 'end': 840, 'date': '2020-05-28'}, {'start': 915, 'end': 975, 'date': '2020-05-28'}, {'start': 1020, 'end': 1200, 'date': '2020-05-28'}, {'start': 1380, 'end': 1410, 'date': '2020-05-28'}, {'start': 600, 'end': 660, 'date': '2020-05-29'}, {'start': 900, 'end': 1320, 'date': '2020-05-29'}]
    # next_monday = '2020-05-25'
    # events = sort_events_by_day(datetime.date.fromisoformat(next_monday), all_events)

    # constraints = [{'start': 0, 'end': 600}, {'start': 1380, 'end': 1439}]
    # # events = {'2020-05-25': [{'start': 660, 'end': 1170, 'date': '2020-05-25'}], '2020-05-26': [{'start': 1080, 'end': 1140, 'date': '2020-05-26'}, {'start': 630, 'end': 960, 'date': '2020-05-26'}], '2020-05-27': [{'start': 630, 'end': 1080, 'date': '2020-05-27'}, {'start': 540, 'end': 600, 'date': '2020-05-27'}], '2020-05-28': [{'start': 600, 'end': 840, 'date': '2020-05-28'}, {'start': 915, 'end': 975, 'date': '2020-05-28'}, {'start': 1020, 'end': 1200, 'date': '2020-05-28'}, {'start': 1380, 'end': 1410, 'date': '2020-05-28'}], '2020-05-29': [{'start': 600, 'end': 660, 'date': '2020-05-29'}, {'start': 900, 'end': 1320, 'date': '2020-05-29'}], '2020-05-30': [], '2020-05-31': []}
    # everything = apply_constraints(events, constraints)
    # # print()
    # # print()
    # # print(everything)

if __name__ == '__main__':
    main()
