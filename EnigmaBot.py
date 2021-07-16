import discord
from discord.ext import tasks, commands

import json
import os
import platform
import math
import random

import sqlite3

import time
from datetime import timedelta, datetime
import pendulum

import aiohttp
import asyncio

client = commands.Bot(command_prefix='sb!')
start_time = time.time()
last_team_pack_day = math.floor((time.time() - 14400) / 86400)
last_rally_ping_day = math.floor((time.time() - 71700) / 86400)

# Authenticate with Discord
@client.event
async def on_ready():
  await client.change_presence(
    activity=discord.Game(name='Storm'),
    status=discord.Status.online)

  print('Authenticated as {} at {}.\r\n'.format(
    client.user, utc_to_formatted_timestamp(
      time.time(),
      config['Time']['TimeZone'],
      config['Time']['TimeFormatCode']
    )
  ))
  
  bot_pulse.start()
  bot_auto_pulse.start()
  bot_auto_status.start()
  bot_ci_events.start()
# bot_team_pack.start()
  bot_rally_ping.start()

@client.command(name='generate')
async def generate_message(ctx):
  await ctx.channel.send("Message generated.")

@tasks.loop(seconds=2)
async def bot_pulse():
  timestamp = utc_to_formatted_timestamp(
    time.time(),
    config['Time']['TimeZone'],
    config['Time']['TimeFormatCode']
  )
  
  channel = client.get_channel(config['Discord']['ChannelIds']['auto/status'])
  message = await channel.fetch_message(config['Discord']['StatusIds']['main'])
  
  await message.edit(content = f"Last check-in at {timestamp} (updates every 2 seconds)")

@tasks.loop(seconds=61)
async def bot_auto_pulse():
  x_coefficient = 1
  
  try:
    cur = dbc.cursor()
    cur.execute('SELECT dealType, dealDataPremium, expireTime FROM ExclusiveEvent ORDER BY uid DESC LIMIT 1')
    data = cur.fetchall()
    
    if data[0][0] == "leaguelevelspeed" and datetime.now() < datetime.strptime(data[0][2], "%Y-%m-%d %H:%M:%S"):
      x_coefficient = data[0][1]
    elif data[0][0] == "cookiesheetspeed":
      x_coefficient = 1 + ((data[0][1] / 100) * 2)
    elif data[0][0] == "milkshakestorm":
      x_coefficient = 1 + ((data[0][1] / 100) * 8)
    else:
      x_coefficient = 1
  except Exception as e:
    x_coefficient = 1
    print("Unable to access SQLite file:\r\n{}".format(e))
    
  for i in config['CookiesIncAccounts']:
    if 'AutoHistory' not in i:
      i['AutoHistoryCompiled'] = {
        "1m": None,
        "5m": None,
        "30m": None,
        "60m": None
      }
      i['AutoHistory'] = [
      ]
    
    try:
      async with aiohttp.ClientSession() as session:
        # update numbers
        raw_data = await async_fetch(session, 'https://ccprodapi.pixelcubestudios.com/Player/Public/{}'.format(
          i['Id']['Public']
        ))
        json_data = json.loads(raw_data)
        current_league = json_data['lifetimeCollected']
    except Exception as e:
      print(e)
    else:
      i['AutoHistory'].append(
        (
          time.time(),
          current_league
        )
      )
      
      i['AutoHistoryCompiled']['1m'] = None
      i['AutoHistoryCompiled']['5m'] = None
      i['AutoHistoryCompiled']['30m'] = None
      i['AutoHistoryCompiled']['60m'] = None
      
      found = [False, False, False, False]
      
      for n, j in enumerate(reversed(i['AutoHistory'])):
        if n == 0:
          continue
        
        time_since_event = time.time() - j[0]
        
        if time_since_event >= 60 and not found[0]:
          i['AutoHistoryCompiled']['1m'] = current_league - j[1]
          found[0] = True
        elif time_since_event >= 300 and not found[1]:
          i['AutoHistoryCompiled']['5m'] = current_league - j[1]
          found[1] = True
        elif time_since_event >= 1800 and not found[2]:
          i['AutoHistoryCompiled']['30m'] = current_league - j[1]
          found[2] = True
        elif time_since_event >= 3600 and not found[3]:
          i['AutoHistoryCompiled']['60m'] = current_league - j[1]
          found[3] = True
      
      if len(i['AutoHistory']) > 64:
        i['AutoHistory'].pop(0)
      
      # send message
      channel = client.get_channel(config['Discord']['ChannelIds']['auto/status'])
      message = await channel.fetch_message(config['Discord']['StatusIds'][json_data['publicId']])
      
      s = f"Account **{i['Name']}** of *<@{i['DiscordUser']}>*\r\n"
      s += f"*{json_data['seasonCollected']:,.0f}* cookies collected this season\r\n"
      s += f"*{json_data['lifetimeCollected']:,.0f}* cookies collected\r\n\r\n"
      
      for k in range(4):
        l_time = [1, 5, 30, 60]
        l_qdc = [
          [
            0.600,
            0.800,
            1.200,
            1.400
          ],
          [
            0.700,
            0.850,
            1.150,
            1.300
          ],
          [
            0.850,
            0.925,
            1.075,
            1.150
          ],
          [
            0.900,
            0.950,
            1.050,
            1.100
          ]
        ]
        
        # rally coefficient calculation
        rally_begin_umod = i['RallyTimeUnixMod']
        rally_end_umod = rally_begin_umod + 3600
        current_umod = time.time() % 86400
        period_begin_umod = current_umod - (l_time[k] * 60)
        
      # print(rally_begin_umod)
      # print(rally_end_umod)
      # print(current_umod)
      # print(period_begin_umod)
      # 
      # print('-------------------------------')
        
        # takes place entirely during rally
        if (period_begin_umod > rally_begin_umod and period_begin_umod < rally_end_umod) and \
           (current_umod > rally_begin_umod and current_umod < rally_end_umod):
          rally_coefficient = 2
        # rally ended during this period
        elif (period_begin_umod > rally_begin_umod and period_begin_umod < rally_end_umod) and \
           not (current_umod > rally_begin_umod and current_umod < rally_end_umod):
          rally_coefficient = ((rally_end_umod - period_begin_umod) * 2 + (current_umod - rally_end_umod) * 1) / (l_time[k] * 60)
        # rally began during this period
        elif not (period_begin_umod > rally_begin_umod and period_begin_umod < rally_end_umod) and \
           (current_umod > rally_begin_umod and current_umod < rally_end_umod):
          rally_coefficient = ((current_umod - rally_begin_umod) * 2 + (rally_begin_umod - period_begin_umod) * 1) / (l_time[k] * 60)
        # no rally
        else:
          rally_coefficient = 1
        
        # data for reporting
        if i['AutoHistoryCompiled'][f'{l_time[k]}m'] is None:
          s += "No additional data available at this time."
          break
        else:
          l_raw = i['AutoHistoryCompiled'][f'{l_time[k]}m']
          l_rate = (l_raw * (60/l_time[k]))
          
          if l_rate < i['AutoRates']['MinimumPerHour'] * rally_coefficient * x_coefficient:
            l_qdesc = "auto is down"
          elif l_rate < i['AutoRates']['ExpectedPerHour'] * l_qdc[k][0] * rally_coefficient * x_coefficient:
            l_qdesc = "well below average"
          elif l_rate < i['AutoRates']['ExpectedPerHour'] * l_qdc[k][1] * rally_coefficient * x_coefficient:
            l_qdesc = "below average"
          elif l_rate < i['AutoRates']['ExpectedPerHour'] * l_qdc[k][2] * rally_coefficient * x_coefficient:
            l_qdesc = "average"
          elif l_rate < i['AutoRates']['ExpectedPerHour'] * l_qdc[k][3] * rally_coefficient * x_coefficient:
            l_qdesc = "above average"
          else:
            l_qdesc = "well above average"
          
          if k < 3:
            l_newline = "\r\n"
          else:
            l_newline = ""
          
          s += f"{l_time[k]} min. average: *{l_raw:,.0f}* ({l_rate:,.0f} / hour; {l_qdesc}){l_newline}"
      
      await message.edit(content = s)

@tasks.loop(seconds=301)
async def bot_auto_status():
  for i in config['CookiesIncAccounts']:
    try:
      async with aiohttp.ClientSession() as session:
        # update numbers
        raw_data = await async_fetch(session, 'https://ccprodapi.pixelcubestudios.com/Player/Public/{}'.format(
          i['Id']['Public']
        ))
        json_data = json.loads(raw_data)
        
        if not 'AutoRatesLive' in i:
          # create key
          i['AutoRatesLive'] = {
            "LastCheck": json_data['lifetimeCollected'],
            "LastDelta": -1,
            "NotifyOnNextOutage": True
          }
          
          print("Initializing {} account at {}, \r\ncurrent lifetime {:,.0f}.\r\n".format(
            i['Name'],
            utc_to_formatted_timestamp(
              time.time(),
              config['Time']['TimeZone'],
              config['Time']['TimeFormatCode']
            ),
            i['AutoRatesLive']['LastCheck']
          ))
        else:
          # update key
          latest_number = json_data['lifetimeCollected']
          
          i['AutoRatesLive']['LastDelta'] = latest_number - i['AutoRatesLive']['LastCheck']
          i['AutoRatesLive']['LastCheck'] = latest_number
          
          delta_period = i['AutoRatesLive']['LastDelta'] * (3600 / 300)
          
          print("Processing {} account at {} ...".format(
            i['Name'],
            utc_to_formatted_timestamp(
              time.time(),
              config['Time']['TimeZone'],
              config['Time']['TimeFormatCode']
            )
          ))
          print("Current lifetime {:,.0f}, \r\noffset from previous: {:,.0f}.\r\n".format(
            i['AutoRatesLive']['LastCheck'],
            i['AutoRatesLive']['LastDelta']
          ))
          
          if delta_period < i['AutoRates']['MinimumPerHour']:
            # auto is malfunctioning
            message = None
            
            if delta_period == 0:
              # auto is completely down
              if json_data['isOnline'] == 0:
                message = "Your {} account is offline.".format(i['Name'])
              else:
                message = "Your {} account is online but not collecting.".format(i['Name'])
            else:
              # auto is partially down
              message = "Your {} account is only collecting {:,.0f} per hour.".format(i['Name'], delta_period)
            
            if i['AutoRatesLive']['NotifyOnNextOutage']:
              channel = client.get_channel(config['Discord']['ChannelIds']['auto/alerts'])
              await channel.send("<@{}> {}".format(
                i['DiscordUser'],
                message
              ))
              
            i['AutoRatesLive']['NotifyOnNextOutage'] = False
          else:
            i['AutoRatesLive']['NotifyOnNextOutage'] = True
    except Exception as e:
      print(e)

@tasks.loop(seconds=15)
async def bot_ci_events():
  for i in config['Events']['Endpoints']:
    async with aiohttp.ClientSession() as session:
      # get all events
      try:
        raw_data = await async_fetch(session, i['Url'])
        json_data = json.loads(raw_data)
      except:
      # print("No active event detected.")
        return None
        
      # access shared DB connection
      dbc = config['Events']['DbConnection']
      cur = dbc.cursor()
      
      cur.execute("SELECT * FROM {} WHERE uid = {}".format(
        i['Table'],
        json_data['uid']
      ))
      active_event = cur.fetchone()
      
      if not active_event:
        ########################
        #     Write to SQL     #
        ########################
        
        # event has not been processed
        all_columns = []
        all_columns += config['Events']['SqlWrite']['Base']
        
        if i['Table'] in config['Events']['SqlWrite']:
          all_columns += config['Events']['SqlWrite'][i['Table']]
        
        column_string = ','.join(all_columns)
        
        value_string = '"{}"'.format(
          '","'.join(
            list(
              map(
                lambda x: str(json_data[x]),
                all_columns
              )
            )
          )
        )
        
        cur.execute("INSERT INTO {} ({}) VALUES ({})".format(
          i['Table'],
          column_string,
          value_string
        ))
        
        # download binary image data
        icon_blob = await async_fetch(session, json_data['btnImageLink'], is_blob=True)
        popup_blob = await async_fetch(session, json_data['bgImageLink'], is_blob=True)
        
        if i['Table'] == 'MilestoneEvent':
          collectable_blob = await async_fetch(session, json_data['collectImageLink'], is_blob=True)
        
        with open("{}.png".format(i['Table']), 'wb') as f:
          f.write(popup_blob)
        
        sql1 = "UPDATE {} SET {} = ? WHERE uid = {}".format(
          i['Table'],
          'btnImage',
          json_data['uid']
        )
        
        sql2 = "UPDATE {} SET {} = ? WHERE uid = {}".format(
          i['Table'],
          'bgImage',
          json_data['uid']
        )
        
        cur.execute(sql1, [sqlite3.Binary(icon_blob)])
        cur.execute(sql2, [sqlite3.Binary(popup_blob)])
        
        if i['Table'] == 'MilestoneEvent':
          sql3 = "UPDATE {} SET {} = ? WHERE uid = {}".format(
            i['Table'],
            'collectImage',
            json_data['uid']
          )
          
          cur.execute(sql3, [sqlite3.Binary(collectable_blob)])
        
        # include raw JSON data for archiving purposes
        sql4 = "UPDATE {} SET {} = ? WHERE uid = {}".format(
          i['Table'],
          'responseString',
          json_data['uid']
        )
        
        cur.execute(sql4, [raw_data])
        cur.execute("UPDATE {} SET startTime = datetime(startTime, 'localTime') WHERE uid = {}".format(i['Table'], json_data['uid']))
        cur.execute("UPDATE {} SET expireTime = datetime(expireTime, 'unixepoch', 'localTime') WHERE uid = {}".format(i['Table'], json_data['uid']))
        
        dbc.commit()
        
        ########################
        # Discord Notification #
        ########################
        
        imageFile = discord.File("{}.png".format(i['Table']))
        
        if int(json_data['expireTime']) > int(time.time()):
          message = "There is a new {} event which will last for {} days and {} hours!".format(
            i['Name'],
            math.floor((int(json_data['expireTime']) - int(time.time())) / 86400),
            math.floor((int(json_data['expireTime']) - int(time.time())) / 3600) % 24
          )
          
          if i['Table'] == "ExclusiveEvent":
            message += "\r\n(reward type \"{}\" with a {}x boost)".format(json_data['dealType'], json_data['dealData'])
          elif i['Table'] == "PuzzleEvent":
            message += "\r\n(reward {:,.0f} of \"{}\")".format(json_data['rewardAmount'], json_data['rewardType'])
          
          channel = client.get_channel(config['Discord']['ChannelIds']['cc2/events'])
          await channel.send(content="<@&{}> {}".format(config['Discord']['ReactionRoleIds']['Event'], message), file=imageFile)

@tasks.loop(seconds=10)
async def bot_team_pack():
  global last_team_pack_day
  
  current_day = math.floor((time.time() - 14400) / 86400)
  
  if (current_day - last_team_pack_day > 0):
    for i in config['CookiesIncAccounts']:
      # send Team Pack
      try:
        async with aiohttp.ClientSession() as session:
          await async_fetch(session, 'https://ccprodapi.pixelcubestudios.com/Gift/TeamMegaGift', {"UID": i["Id"]["Private"]})
          last_team_pack_day = math.floor((time.time() - 14400) / 86400)
      except Exception as e:
        print(e)

@tasks.loop(seconds=10)
async def bot_rally_ping():
  global last_rally_ping_day
  
  current_day = math.floor((time.time() - 71700) / 86400)
  
  if (current_day - last_rally_ping_day > 0):
    last_rally_ping_day = math.floor((time.time() - 71700) / 86400)
    
    channel = client.get_channel(config['Discord']['ChannelIds']['cc2/rally'])
    to_send = f"<@&{config['Discord']['ReactionRoleIds']['Rally']}> Team rally starts in five minutes!"

    await channel.send(to_send)
    return to_send

@commands.cooldown(1, 1, commands.BucketType.user)
@client.command(aliases=['lucky'])
async def command_lucky(message):
  if random.random() > 0.99:
    await message.send("<@{}> YOU'RE A LUCKY BOI!!".format(message.author.id))
  else:
    await message.send("You're not too lucky this time. Try again.")

@commands.cooldown(1, 1, commands.BucketType.user)
@client.command(aliases=['numbers', 'number', 'n'])
async def command_numbers(ctx):
  id = ctx.author.id
  current = None
  
  os.chdir(f"{os.path.dirname(__file__)}/NumberGame")
  
  if not os.path.isfile(f"{str(id)}.numbergame"):
    with open(f"{str(id)}.numbergame", "x") as f:
      await ctx.send("<@{}>: Your profile has been created. Enjoy playing!".format(id))
  else:
    with open(f"{str(id)}.numbergame", "r") as f:
      raw_data = f.read()
      
      if not raw_data:
        current = 1
      else:
        current = int(raw_data)
      
      f.close()

    with open(f"{str(id)}.numbergame", "w+") as f:
      new = None
      output = None
      return_message = lambda x, y, z: "{}\r\nPrevious Number: {}\r\nNew Number: {}".format(x, y, z)
      
      rseed = random.random()
          
      if current >= 1:
        if rseed > 0.999:
          new = current**10
          output = return_message("YOU GOT THE EXPONENTIAL BOOST TO END ALL EXPONENTIAL BOOSTS!", current, new)

        elif rseed > 0.99:
          new = current**random.randint(6, 9)
          output = return_message("YOU GOT A MASSIVE EXPONENTIAL BOOST!", current, new)
        
        elif rseed > 0.98:
          new = current**random.randint(3, 5)
          output = return_message("YOU GOT AN EXPONENTIAL BOOST!", current, new)
        
        elif rseed > 0.97:
          new = current**2
          output = return_message("Your number was squared!", current, new)
        
        elif rseed > 0.95:
          coeff = random.randint(8, 11)
          new = current*coeff
          output = return_message("Your number was multiplied by {}!".format(coeff), current, new)
        
        elif rseed > 0.9:
          coeff = random.randint(4, 7)
          new = current*coeff
          output = return_message("Your number was multiplied by {}!".format(coeff), current, new)
        
        elif rseed > 0.85:
          coeff = random.randint(4, 7)
          new = current*coeff
          output = return_message("Your number was multiplied by {}!".format(coeff), current, new)
        
        elif rseed > 0.8:
          new = current*3
          output = return_message("Your number was tripled!", current, new)
        
        elif rseed > 0.7:
          new = current*2
          output = return_message("Your number was doubled!", current, new)
        
        elif rseed > 0.6:
          coeff = random.randint(10, 19)
          new = current+coeff
          output = return_message("{} was added to your number!".format(coeff), current, new)
        
        elif rseed > 0.5:
          coeff = random.randint(5, 9)
          new = current+coeff
          output = return_message("{} was added to your number!".format(coeff), current, new)
        
        elif rseed > 0.4:
          coeff = random.randint(3, 4)
          new = current+coeff
          output = return_message("{} was added to your number!".format(coeff), current, new)
        
        elif rseed > 0.3:
          new = current+2
          output = return_message("2 was added to your number!", current, new)
        
        elif rseed > 0.2:
          new = current+1
          output = return_message("1 was added to your number!", current, new)
        
        elif rseed > 0.01:
          new = current
          output = return_message("Nothing happened to your number!", current, new)
        
        elif rseed > 0.0001:
          new = -1
          output = "Bad luck! You're in number purgatory! Keep playing to get out of it!"
        
        else:
          new = -2
          output = "Extremely bad luck! You're in serious number purgatory! Keep playing to get of it!"
      
      elif current == -2 and random.random() < 0.995:
        output = "You're still in number purgatory! Keep playing to get out of it!"
        new = -2
      elif current == -1 and random.random() < 0.95:
        output = "You're still in number purgatory! Keep playing to get out of it!"
        new = -1
      else:
        output = "You've escaped number purgatory! Your number has been reset to 1!"
        new = 1
      
      f.seek(0)
      f.write(str(new))
      
      final_message = "<@{}>: {}".format(id, output)
      
      if len(final_message) > 1999:
        f.close()
        os.remove(f"{str(id)}.numbergame")
        await ctx.send("CONGRATULATIONS <@{}>! You won the Number Game by exceeding the Discord message length limit! A Win has been added to your account!".format(id))
        
        if not os.path.isfile(f"{str(id)}.numberwins"):
          with open(f"{str(id)}.numberwins", "x") as g:
            pass
        
        current_wins = None
  
        with open(f"{str(id)}.numberwins", "r") as g:
          raw_data = g.read()
          
          if not raw_data:
            current_wins = 0
          else:
            current_wins = int(raw_data)
          
          g.close()
  
        with open(f"{str(id)}.numberwins", "w+") as g:
          g.seek(0)
          g.write(str(current_wins + 1))
      else:
        await ctx.send(final_message)
  
  os.chdir(f"{os.getcwd()}/..")

@commands.cooldown(1, 1, commands.BucketType.user)
@client.command(aliases=['numberwins', 'numberwin', 'nw'])
async def command_numberwins(ctx):
  id = ctx.author.id
  current = None
  os.chdir(f"{os.getcwd()}/NumberGame")
  
  if not os.path.isfile(f"{str(id)}.numberwins"):
    await ctx.send("<@{}>: You have never won the Number Game! Get a win by playing `sb!numbers`!".format(id))
  else:
    with open(f"{str(id)}.numberwins", "r") as f:
      raw_data = int(f.read())
      if raw_data == 1:
        plural = ""
      else:
        plural = "s"
      await ctx.send("<@{}>: You have won the number game {} time{}.".format(id, raw_data, plural))
  
  os.chdir(f"{os.getcwd()}/..")

# prints version info
@client.command(aliases=['ver', 'version', 'build', 'about', 'inf', 'info'])
async def command_version(ctx):
  to_send = '**{0} {1}**\r\nUptime: {2}\r\nHost OS: {3}\r\nCopyright © 2021 Darren R. Skidmore. All rights reserved.'.format(config['Core']['ApplicationName'], config['Core']['ApplicationBuild'], timedelta((time.time()-start_time)/86400), platform.platform())
  await ctx.channel.send(to_send)
  return to_send

@client.event
async def on_command_error(ctx, error):
  if isinstance(error, commands.CommandOnCooldown):
    await ctx.send("<@{}> Slow down, please! (1 second cooldown)".format(ctx.author.id))
  else:
    await ctx.send(f"A fatal error occurred. The developer <@{config['Discord']['DiscordOwnerId']}> has been notified:\r\n`{error}`")
    print(error)

def utc_to_formatted_timestamp(i, t, f):
  time_zone = pendulum.timezone(t)
  time_object = datetime.fromtimestamp( i, time_zone )
  time_object_tz = time_object.astimezone()
  return time_object.strftime(f)

async def async_fetch(session, url, data=None, requires_content_type=False, is_blob=False):
  if requires_content_type:
    headers = {'Content-type': 'application/x-www-form-urlencoded', 'User-agent': '{0[ApplicationName]} {0[ApplicationBuild]}'.format(config['Core'])}
  else:
    headers = {'User-agent': '{0[ApplicationName]} {0[ApplicationBuild]}'.format(config['Core'])}

  if not data:
    async with session.get(url, headers=headers) as response:
      if is_blob:
        return await response.read()
      else:
        return await response.text()
  else:
    async with session.post(url, headers=headers, data=data) as response:
      if is_blob:
        return await response.read()
      else:
        return await response.text()

if __name__ == '__main__':
  with open('ebc.json', 'r') as f: 
    config = json.load(f)
  
  dbc = sqlite3.connect(config['Events']['DbFile'])
  config['Events']['DbConnection'] = dbc
  
  client.run(config['Core']['AuthToken'])