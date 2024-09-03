# This Python program is a template for an automated trading strategy at IB that uses the IB API.
# It uses a simple EMA5 moving average and 5-min SPY bars.  If close of a 5-min bar is above the
# prior bar's EMA value, and have no position, then go long. Reverse for short. Exits are based on
# profit and loss stops placed as a bracket order wuth the initial entry.  Much of the core code is
# here, but  this is just a simple example ONLY, and should not be used with real money.
# Randy May. Last updated 8/17/24.

import sys
import pandas as pd
import time
import numpy as np
#import logging
#import requests				# For receiving API messages
#import json
import threading
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import *
from datetime import date, datetime, timedelta
from pytz import timezone
#from pyti.hull_moving_average import hull_moving_average as hma
from pyti.exponential_moving_average import exponential_moving_average as ema
from decimal import Decimal
#import asyncio			# Need to run: pip install asyncio

ib_event = threading.Event()
ib_event.clear()

global slope_min
global spy_snapshot		# Variable for 5s SPY quote updates (for trailing stops)

fillprice = 1.0			# Declare here so it is global?
iposition = 0           # Use to flag long (1), short (-1), or no position (0)
# Adjust parameters below as needed for 5-min SPY bars
EMA_length = 5			# EMA length for trades (best for SPY 2022-2024 as of 8/24/24)
Profit_stop = 1.0		# Placeholder until assigned actual SPY price
Stop_loss = 1.0			# Ditto (declared here so global?)
profit_offset = 3.20	# Offset for profit stop SPY price for orders
stop_offset = 3.40		# Ditto for stop losses (both relative to initial fill price)
spy_snapshot = 1.0
#ndonchian = 11
dfilter = 0.80			# Donchian width filter (minimum to take a trade)
#is_ = ndonchian + 1  # First point in array
#iend = nbars  # Last point in the day

class IBapi(EWrapper, EClient):
	def __init__(self):
		EClient.__init__(self, self)
		self.historical_bar_data = []
		self.portfolio= {}

	def nextValidId(self, orderId: int):
		super().nextValidId(orderId)
		self.nextorderId = orderId
		print('The next valid order id is: ', self.nextorderId)

	def orderStatus(self, orderId, status, filled, remaining, avgFullPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
		#global fillprice
		print('orderStatus - orderid:', orderId, 'status:', status, 'filled', filled, 'remaining', remaining, 'lastFillPrice', lastFillPrice)
	
	def openOrder(self, orderId, contract, order, orderState):
		print('openOrder id:', orderId, contract.symbol, contract.secType, '@', contract.exchange, ':', order.action, order.orderType, order.totalQuantity, orderState.status)

	def execDetails(self, reqId, contract, execution):
		global fillprice				# This seems to be necessary to assign fillprice,  despite fillprice being defined at the top
		print('Order Executed: ', reqId, contract.symbol, contract.secType, contract.currency, execution.shares, execution.price)
		now = datetime.now()			# Current date and time
		year = now.strftime("%Y")
		month = now.strftime("%m")
		day = now.strftime("%d")
		hour = now.strftime("%H")		# 24-hr format, but local time in Tucson, AZ
		NYhour = int(hour) + dtime		# New York hour (+3 from Tucson, but +2 come Nov 1 and DST removal)
		minute = now.strftime("%M")		# Range is 0-60
		second = now.strftime("%S")		# Range is 0-60 month
		dp = month + "/" + day + "/" + year
		tp = str(NYhour) + ":" + minute + ":" + second
		fileout = open("logfile1.txt", "a+")
		tempstring = dp + " " + tp + " " + contract.symbol + " " + str(iposition) + " " + str(execution.shares) +  " " + str(execution.price) + "\n"
		fillprice = execution.price		# This gives "variable not accessed" if don'have "global fillprice" within this function
		fileout.write("\n")
		fileout.write(tempstring)
		fileout.write("Inside execDetails: fillprice = " + str(fillprice))
		fileout.write("\n")
		fileout.close()
	 
	def historicalData(self, reqId, bar):
		super().historicalData(reqId, bar)
		fmt_str = '%Y%m%d'
		if ':' in bar.date: fmt_str = '%Y%m%d %H:%M:%S'
		self.historical_bar_data.append({'Date':datetime.strptime(bar.date,fmt_str),
												'Open':bar.open,'High':bar.high,'Low':bar.low,'Close':bar.close,'Volume':bar.volume*1000})
	def historicalDataEnd(self, reqId: int, start: str, end: str):
		super().historicalDataEnd(reqId, start, end)
		ib_event.set()

# Below added 2/19/22 to try and get snapshot of most recent price
	def tickPrice(self, reqId, tickType, price, attrib):
		global spy_snapshot
		if tickType <= 2 and reqId == 1:
			spy_snapshot = price
			print('The current ask price is: ', price)
			print('spy_snapshot = ', spy_snapshot)

	def updatePortfolio(self, contract: Contract, position: float, marketPrice: float, marketValue: float,
						averageCost: float, unrealizedPNL: float, realizedPNL: float, accountName: str):
		super().updatePortfolio(contract, position, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, accountName)
		if position:
			d_item = {"position":position, 'marketPrice':marketPrice, 'contract':contract,'strikes':[],
					  'expiration_dates':[], 'unrealizedPNL':unrealizedPNL,'averageCost':averageCost}
			if contract.secType == 'STK':
				self.portfolio[contract.symbol]= d_item

	def accountDownloadEnd(self, accountName: str):
		super().accountDownloadEnd(accountName)
		ib_event.set()

	def account_updates(self):
		self.reqAccountUpdates(True, self.account)
		ib_event.wait()
		ib_event.clear()
		self.reqAccountUpdates(False, self.account)		# stop the updating loop

	def ib_connect(self, host, port, clientId, account):
		self.connect(host=host, port=port, clientId=clientId)
		self.account = account

	def go_long(self, symbol, position_size):
		global iposition
		self._place_order(symbol=symbol, position_size=position_size, action='BUY')
		iposition = 1
		print("Placed order to BUY " + str(position_size) + " shares of " + symbol)
		print("In go_long: iposition = " + str(iposition) + "\n")

	def go_short(self, symbol, position_size):
		global iposition
		self._place_order(symbol=symbol, position_size=position_size, action='SELL')
		iposition = -1
		print("Placed order to SELL " + str(position_size) + " shares of " + symbol)
		print("In go_short: iposition = " + str(iposition) + "\n")

# Primary order placing function
	def _place_order(self, symbol, position_size, action):
		contract = Contract()
		contract.symbol = symbol
		contract.secType = "STK"
		contract.exchange = "SMART"
		contract.currency = "USD"
		order = Order()
		order.action = action
		order.orderType = "MKT"
		order.totalQuantity = position_size
		order.eTradeOnly = False
		order.firmQuoteOnly = False
		order.transmit = True

		self.nextorderId +=1
		self.placeOrder(orderId=self.nextorderId, contract=contract, order=order)

		return order

# Bracket order group for placing takeprofit and stoploss orders
	def go_bracket_long(self, symbol, position_size, limitPrice, takeProfitLimitPrice, stopLossPrice):		# Attempt at bracket order
		self.nextorderId +=1
		print("Bracket_long: self.nextorderId = ", self.nextorderId)
		BracketOrder(parentOrderId=self.nextorderId, action='BUY',quantity=position_size, limitPrice=limitPrice, takeProfitLimitPrice=takeProfitLimitPrice, stopLossPrice=stopLossPrice)
		print("Placed bracket order to BUY " + str(position_size) + "shares of " + symbol + "\n")
		print("In go_bracket_long: limitPrice = " + str(limitPrice) + "\n")
		print("In go_bracket_long: takeProfitLimitPrice = " + str(takeProfitLimitPrice) + "\n")
		print("In go_bracket_long: stopLossPrice = " + str(stopLossPrice) + "\n")

	def go_bracket_short(self, symbol, position_size, limitPrice, takeProfitLimitPrice,stopLossPrice):		# Add limit, profit and stop prices
		self.nextorderId +=1
		print("Bracket_short: self.nextorderId = ", self.nextorderId)
		BracketOrder(parentOrderId=self.nextorderId, action='SELL',quantity=position_size, limitPrice=limitPrice, takeProfitLimitPrice=takeProfitLimitPrice, stopLossPrice=stopLossPrice)
		print("Placed bracket order to SELL " + str(position_size) + "shares of " + symbol + "\n")
		print("In go_bracket_short: limitPrice = " + str(limitPrice) + "\n")
		print("In go_bracket_short: takeProfitLimitPrice = " + str(takeProfitLimitPrice) + "\n")
		print("In go_bracket_short: stoplossPrice = " + str(stopLossPrice) + "\n")

# Should this be indented as above?  That would put them in the IBapi class but it seems to work in test program as it is below.
def BracketOrder(parentOrderId:int, action:str, quantity:Decimal, 
                 limitPrice:float, takeProfitLimitPrice:float, 
                 stopLossPrice:float):
# Are indentions correct here?     
# Start with the main or "parent" order
	print("In BracketOrder, parentOrderId = ", parentOrderId)
	parent = Order()
	parent.orderId = parentOrderId
	parent.eTradeOnly = False
	parent.firmQuoteOnly = False
	parent.action = action
	parent.orderType = "LMT"
	parent.totalQuantity = quantity
	parent.lmtPrice = limitPrice
	parent.transmit = False		# Set parent to false,  as well as next child. Final child gets True
 
	takeProfit = Order()
	takeProfit.orderId = parent.orderId + 1
	takeProfit.eTradeOnly = False
	takeProfit.firmQuoteOnly = False
	takeProfit.action = "SELL" if action == "BUY" else "BUY"
	takeProfit.orderType = "LMT"
	takeProfit.totalQuantity = quantity
	takeProfit.lmtPrice = takeProfitLimitPrice
	takeProfit.parentId = parentOrderId
	takeProfit.transmit = False
 
	stopLoss = Order()
	stopLoss.orderId = parent.orderId + 2
	stopLoss.eTradeOnly = False
	stopLoss.firmQuoteOnly = False
	stopLoss.action = "SELL" if action == "BUY" else "BUY"
	stopLoss.orderType = "STP"
	stopLoss.auxPrice = stopLossPrice
	stopLoss.totalQuantity = quantity
	stopLoss.parentId = parentOrderId
	stopLoss.transmit = True			# This activates all the other orders
# Now fire in the orders
	print("Firing Parent order")	
	app.placeOrder(parent.orderId, spy_contract, parent)
	print("Firing takeProfit order")	
	app.placeOrder(takeProfit.orderId, spy_contract, takeProfit)
	print("Firing stopLoss order")	
	app.placeOrder(stopLoss.orderId, spy_contract, stopLoss)
 
	bracketOrder = [parent, takeProfit, stopLoss]
	return bracketOrder

# ------------------------------------------------------------------------------
def run_loop():
	app.run()			

app = IBapi()
app.ib_connect(host='127.0.0.1', port=7497, clientId=127, account='1')			# Port 7497 is for paper trading.
#app.ib_connect(host='127.0.0.1', port=7496, clientId=127, account='xxxxxxx')	# Removed account number

#Start the socket in a thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

time.sleep(2)    # Sleep interval to allow time for connection to the server

# Define the number of shares of SPY to trade (use 20 for testing)
cnt_spy = 10			# SPY
#cnt_mes = 1			# MES futures (for later)
print("Share counts defined\n")

dtime = 0							# NC to NY time difference (in NC now, 2024, so no need to adjust)

# Below is a function to create a stock contract (from web IB tutorial at algotrading101.com).
def Stock_contract(symbol, secType='STK', exchange='SMART', currency='USD'):
		''' custom function to create stock contract '''
		contract = Contract()
		contract.symbol = symbol
		contract.secType = secType
		contract.exchange = exchange
		contract.currency = currency
		return contract

def Futures_contract(symbol, secType='FUT', exchange='GLOBEX', currency='USD'):
		''' custom function to create futures contract '''
		contract = Contract()
		contract.symbol = symbol
		contract.secType = secType
		contract.exchange = exchange
		contract.currency = currency
		contract.LastTradeOrContractMonth = '202412'		# Dec 2024 = YYYYMM, change at rollovers
		return contract

# Then repeat the same idea for the orders:
def Stock_order(symbol, secType='STK', exchange='SMART', currency='USD'):
		''' custom function to create stock order '''
		contract = Contract()
		contract.symbol = symbol
		contract.secType = secType
		contract.exchange = exchange
		contract.currency = currency
		return contract

def Futures_order(symbol, secType='FUT', exchange='GLOBEX', currency='USD'):
		''' custom function to create futures order '''
		contract = Contract()
		contract.symbol = symbol
		contract.secType = secType
		contract.exchange = exchange
		contract.currency = currency
		contract.LastTradeOrContractMonth = '202412'		# Dec 2024 = YYYYMM, change at rollovers
		return contract

# Now create the contracts for all tickers
spy_contract = Stock_contract('SPY')
# qqq_contract = Stock_contract('QQQ')
print("Stock Contracts Defined\n")

# And create the orders as above by just calling this with the ticker:
spy_order = Stock_order('SPY')
# qqq_order = Stock_order('QQQ')
print("Order Contracts Defined\n")

# Request historical candles (5 minute bars, 2 days) so that EMA can be formed from prior data
def _req_historical_candles(ib_contract, app):
	app.reqHistoricalData(1, ib_contract, '', '2 D', '5 mins', 'BID', 1, 1, False, [])
	ib_event.wait()
	ib_event.clear()
	_df = pd.DataFrame(app.historical_bar_data)
	app.historical_bar_data = []
	return _df

spy_df = _req_historical_candles(ib_contract=spy_contract, app=app)

# Get initial EMA values
ema_spy = ema(spy_df['Close'].values, EMA_length)               # EMA for SPY
print("Initial EMA calculated for SPY\n")

# Open a log file to write trade data
fileout = open("logfile1.txt", "a+")

print ("Starting program for the day ... waiting on next 5-min bar\n")
fileout.write ("Starting program for the day ... waiting on next 5-min bar\n")

# Get the current NY time after initializing some variables
NYhour = 0				# Initialize this to zero to start
hour = 0				# Ditto
minute = 0				# Ditto
startflag = 0			# Flag that start of trading has not yet begun
combined_hs = 0			# Variable to hold a time value like 941, 1553, etc.
# For 11-point Donchian,  can't start until bar 11 = 10:20 am
t_start = 1017			# Start trades just before 10:20 am if using Donchian filter
#t_start = 947			# 9:47 am New York time (don't start until bar 950 = first valid EMA5 point)
t_end = 1600			# 4:00 pm Hew York time
min_bars = 5			# Trades on 5 minute bars
updateflag = 0			# Flag that a new 5-minute update is needed

# Note: This program is assumed to have been started shortly before market open and is manually closed after
# market close.  So no need to poll for 9:30am ... just bracket the order placement process for regular hours.
# For new 5-min SPY, first valid EMA bar is bar that closes at 9:50am (935, 940, 945 are first 3, and scheme
# uses current bar close > EMA for PRIOR bar). So start program manually at about 9:47am.
now = datetime.now()			# Current date and time
year = now.strftime("%Y")
month = now.strftime("%m")
day = now.strftime("%d")
hour = now.strftime("%H")		# 24-hr format
NYhour = int(hour) + dtime		# New York hour (+3 from Tucson, but +2 come Nov 1 and DST removal)
minute = now.strftime("%M")		# Range is 0-60
second = now.strftime("%S")		# Range is 0-60
combined_hs = int(NYhour)*100 + int(minute)		# Form this continuously throughout the day

print("Starting minute = ", minute)
print("combined_hs = ", combined_hs)
date_print = day + " " + month + " " + year
time_print = str(NYhour) + " " + minute + " " + second
fileout.write("Current day, month, year = %s\n" % date_print)
fileout.write("Current NYhour, minute, second = %s\n" % time_print)
fileout.write("\r\n")
fileout.close()
#fileout.flush()

# Get a new time stamp and wait for minute to hit the next target value (a 5-min boundary). Note that
# all values returned from strftime() function are strings, so to use them in numerical calculations 
# need to do int(value) to convert to an integer.

while ((combined_hs > 700) and (combined_hs < 1700)):		# MASTER WHILE LOOP FOR entire day
# If block below defines actions to take AT each 5-min bar interval.  The "else" part is way below...
	if (int(minute) % min_bars == 0):						# If on a 5 minute interval (so can't use 15:57 below, eg.)

# First check if at the last bar of the day, and if so close any open positions and exit
		if((int(hour)==15) and (int(minute)==55)):			# Deal with any open orders at 15:55 pm bar close
			app.account_updates()							# Get current SPY position
			spy_current_pos = app.portfolio['SPY']['position'] if 'SPY' in app.portfolio.keys() else 0
			if(spy_current_pos == 0):
				print("No open SPY positions at 15:55 bar, exiting program \n")
				fileout.write("No open SPY positions at 15:55 bar, exiting program")
				fileout.write("\n")
				fileout.close()
				sys.exit()					# Terminate program execution
			if(spy_current_pos > 0):
				print("Found open long SPY positions at 15:55 bar, closing at market \n")
				fileout.write("Found open long SPY positions at 15:55 bar, closing at market")
				fileout.write("\n")
				fileout.close()
				app.go_short(symbol='SPY', position_size=cnt_spy)		# Exit long position at market
				time.sleep(2)
#				app.reqGlobalCancel()		# Cancels all open orders (not needed ... exiting parent kills the child orders)
				sys.exit()					# Terminate program execution
			if(spy_current_pos < 0):
				print("Found open short SPY positions at 15:55 bar, closing at market \n")
				fileout.write("Found open short SPY positions at 15:55 bar, closing at market")
				fileout.write("\n")
				fileout.close()
				app.go_long(symbol='SPY', position_size=cnt_spy)		# Exit short position at market
				time.sleep(2)
#				app.reqGlobalCancel()		# Cancels all open orders
				sys.exit()					# Terminate program execution
#
# Also need code here to monitor the stop and limit exit orders so that know when they are hit. At present, the only way
# to know this is to do an account inquiry, and that happens every 5 minutes, but if manually exit a trade to go flat,
# account inquiry still reports an open position.
#
# 		print("SPY current position is: ", spy_current_pos)
		fileout = open("logfile1.txt", "a+")
		print ("Hit a 5-min bar close, getting new data for bar close at minute: ", int(minute))
		minute_string = "Getting new data for bar close at minute " + minute
		fileout.write("\n")
		date_print = "Current m/d/y = " + month + "-" + day + "-" + year
		time_print = "Current NY hr, min, sec = " + str(NYhour) + ":" + minute + ":" + second
		fileout.write(date_print)
		fileout.write("\n")
		fileout.write(time_print)
		fileout.write("\n")
		time.sleep(3)			# Delay 3s to ensure at least 3s after the bar close for valid data

		# 1) Get latest prices (at close of each 5-minute bar)
		spy_df = _req_historical_candles(ib_contract=spy_contract, app=app)
		time.sleep(0.5)
		spy_last = spy_df['Close'].values[-1]			# Most recent closing bar price

		print ("Finished getting new 5-min bar data\n")
		print("spy_last = $", spy_last)
		fileout.write("Finished getting new 5-min bar data\n")
		fileout.write(f"SPY last = {spy_last:.3f}")
		fileout.write("\n")

		# 1.5) Get Donchian width by brute force for prior 11 SPY values.  Note that this is the width at the
		# present bar only, which is all that is needed for a trade filter
		p11 = spy_df['Close'].values[-11]		# Value 11 bars ago (-1  is present bar, so -11 is 11 bars ago)
		p10 = spy_df['Close'].values[-10]		# Value 10 bars ago, etc.
		p9 = spy_df['Close'].values[-9]			
		p8 = spy_df['Close'].values[-8]			
		p7 = spy_df['Close'].values[-7]			
		p6 = spy_df['Close'].values[-6]			
		p5 = spy_df['Close'].values[-5]			
		p4 = spy_df['Close'].values[-4]			
		p3 = spy_df['Close'].values[-3]			
		p2 = spy_df['Close'].values[-2]			
		p1 = spy_df['Close'].values[-1]	
		pmax=max(p11, p10, p9, p8, p7, p6, p5, p4, p3, p2, p1)		# Max of last 11 values
		pmin=min(p11, p10, p9, p8, p7, p6, p5, p4, p3, p2, p1)		# Min of last 11 values
		dwidth = pmax - pmin					# Donchian width in SPY points
		print("Donchian max, min = ", pmax, pmin)
		print(f"Donchian width = {dwidth:.3f}")
		fileout.write(f"Donchian width = {dwidth:.3f}")
		fileout.write("\n")

# Below is code from a Fortran to Python online converter
#		for ii in range(is_, iend + 1):				  # eg. 10 to end of file
#    		pmax = -5.0e30
#    		pmin = 5.0e30
#    		for k in range(ii - ndonchian, ii):  # eg. i=1, 2, ... 20
#        		if spy_df['Close'].values[k] > pmax:
#            		pmax = spy_df['Close'].values[k]  # Find min and max over prior ndonchan range
#        		if spy_df['Close'].values[k] < pmin:
#            		pmin = spy_df['Close'].values[k]
#    	dwidth = pmax - pmin  # Width of Donchian channel (used to filter trades)

		# 2) Update EMA array with latest values for each ticker
		ema_spy = ema(spy_df['Close'].values, EMA_length)                 # EMA length
		print ("Finished forming new EMA array\n")

		# 3) Check value of price now vs. EMA 1 bar ago and store the difference (call this spy_diff)
		ema_last = ema_spy[-2]			# Prior bar (-1 is current value)
#		spy_last = spy_df['Close'].values[-1]		# Done above when prices updated
		price_now = spy_last
		spy_diff = spy_last - ema_last				# Difference price now vs. prior bar EMA5
		print("SPY now = ", spy_last)
		print(f"EMA last = {ema_last:.3f}")
		print(f"spy_diff = {spy_diff:.3f}")
		fileout.write(f"EMA last = {ema_last:.3f}")
		fileout.write("\n")
		fileout.write(f"SPY - EMA = {spy_diff:.3f}")
		fileout.write("\n")

#		fileout = open("logfile1.txt", "a+")
		app.account_updates()
		time.sleep(1.0)					# Give 1s for results to be available

# Use average price from above call for fillprice below (for prints and file)
		spy_current_pos = app.portfolio['SPY']['position'] if 'SPY' in app.portfolio.keys() else 0
		print("SPY current position is = ", spy_current_pos)
		fileout.write("SPY current position  = " + str(spy_current_pos))
		fileout.write("\n")
#		fileout.write("Outside execDetails: fillprice  = " + str(fillprice))
#		fileout.write("\n")
# Is below average cost only for open trades, or across all trades made today?
		spy_avgCost = app.portfolio['SPY']['averageCost'] if 'SPY' in app.portfolio.keys() else 0
		print(f"SPY average cost is: {spy_avgCost:.3f}")
		fileout.write(f"SPY average cost = {spy_avgCost:.3f}")
		fileout.write("\n")
		print ("Finished account download\n")
		fileout.flush()

# Below is inside loop for executing trades. Need to form a Profit_exit price and a Stop_exit price based on entry
# price.  These are absolute SPY price levels for the profit stop and stop loss orders. Below, if eiither is hit
# then need to execute the exit order and cancel the other side (unless can enter a bracket order at the start).
# If can get bracket order working, then can simply check for an entry based on price and EMA5, and when met
# place the bracket order which covers the entry, profit stop and stop loss.
#		if ((combined_hs > t_start) and (combined_hs < t_end)):		# Allow orders only during regular hours
		if ((combined_hs > t_start) and (combined_hs < t_end)):		# Allow orders only during regular hours

# If presently flat then reenter on EMA/Price requirements (SPY latest bar price ? last bar EMA for long,
# opposite for shorts). Need to make sure fillprice variable has correct value!!
			if (spy_diff > 0 and spy_current_pos == 0 and dwidth > dfilter):		# Adds Donchian width filter of 0.80
#			if (spy_diff > 0 and spy_current_pos == 0):
				print("Conditions met for a new entry long\n")
				fileout.write("Conditions met for a new entry long")
				fileout.write("\n")
# fillprice is not updating properly, so use price at 5-min bar close instead of fillprice for now
				Profit_stop = spy_last + profit_offset			# Profit stop price for longs (make 4.0 a variable!)
				Stop_loss = spy_last - stop_offset				# Stop loss price for longs (make 1.0 a variable!)
				limitPrice = spy_last +  0.10					# Allow some tolerance to ensure order fills at limit entry price
				print("New long, Profit_stop = $", Profit_stop)
				print("New long, Stop_loss = $", Stop_loss)
				fileout.write("New long, Profit_stop = " + str(Profit_stop))
				fileout.write("\n")
				fileout.write("New long, Stop_loss = " + str(Stop_loss))
				fileout.write("\n")
				print("Placing bracket for long 10 SPY with stops\n")
				app.go_bracket_long(symbol='SPY', position_size=cnt_spy, limitPrice=limitPrice,takeProfitLimitPrice=Profit_stop, stopLossPrice=Stop_loss)		# New long stops
				time.sleep(0.5)

			if (spy_diff < 0 and spy_current_pos == 0 and dwidth > dfilter):
#			if (spy_diff < 0 and spy_current_pos == 0):
				print("Conditions met for a new entry short\n")
				fileout.write("Conditions met for a new entry short")
				fileout.write("\n")
# fillprice is not updating properly, so use price at 5-min bar close instead of fillprice for now
				Profit_stop = spy_last - profit_offset			# Profit stop price for shorts (make 4.0 a variable!)
				Stop_loss = spy_last + stop_offset				# Stop loss price for shorts (make 1.0 a variable!)
				limitPrice = spy_last -  0.10					# Allow some tolerance to ensure order fills at limit entry price
				print("New short, Profit_stop = ", Profit_stop)
				print("New short, Stop_loss = ", Stop_loss)
				fileout.write("New short, Profit_stop = " + str(Profit_stop))
				fileout.write("\n")
				fileout.write("New short, Stop_loss = " + str(Stop_loss))
				fileout.write("\n")
				print("Placing bracket for short 10 SPY with stops\n")
				app.go_bracket_short(symbol='SPY', position_size=cnt_spy, limitPrice=limitPrice,takeProfitLimitPrice=Profit_stop, stopLossPrice=Stop_loss)		# New short stops
				time.sleep(0.5)

		fileout.flush()

		print("Delaying 60s for minute variable to increment by 1")
		time.sleep(60)					# Delay 60s to force "minute" to the next value

		ts = time.time()				# Returns a unix time w.r.t Jan 1, 1970
		now = datetime.now()			# current date and time
		hour = now.strftime("%H")		# 24-hr format, but local time in Tucson
		NYhour = int(hour) + dtime		# New York hour (+3 from Tucson, but +2 come Nov 1 and DST removal)
		minute = now.strftime("%M")		# Range is 0-60, update here for next loop check at top
		combined_hs = int(NYhour)*100 + int(minute)		# Form this continuously throughout the day
	else:					# If NOT a 5-minute bar, just count down the time until next bar is ready
		ts = time.time()				# Returns a unix time w.r.t Jan 1, 1970 (do I need this?)
		now = datetime.now()			# current date and time
		hour = now.strftime("%H")		# 24-hr format, but local time in Tucson
		NYhour = int(hour) + dtime		# New York hour (+3 from Tucson, but +2 come Nov 1 and DST removal)
		minute = now.strftime("%M")		# Range is 0-60
		second = now.strftime("%S")		# Range is 0-60
		combined_hs = int(NYhour)*100 + int(minute)		# Form this continuously throughout the day
		print ("Present minute, second: ", minute, second)		# Count down on terminal so can watch/check
		time.sleep(2)					# Delay for 2s before trying again (or less? ... don't want to mmiss the next bar close)

# Try getting account updates more often during this period to see if can get it to update properly after sales
#		if (int(second) == 30):			# If on a 30 second boundary
#			print("Between 5-min bars, 30s intervals, account update")
#			app.account_updates()
#			time.sleep(1.0)					# Give 1s for results to be available
#			print (app.portfolio)			# Will this work?
#			spy_current_pos = app.portfolio['SPY']['position'] if 'SPY' in app.portfolio.keys() else 0
#			print("SPY current position is = ", spy_current_pos)
#			spy_avgCost = app.portfolio['SPY']['averageCost'] if 'SPY' in app.portfolio.keys() else 0
#			print(f"SPY average cost is: {spy_avgCost:.3f}")


# First 3 lines below work ot get most recent SPY price, but is a lot of API calls (20 per  minute). Could do this for entire
# trading scheme where watch for profitstop or stoploss via brute force and enter market orders if hit (so no bracket or OCO
# orders ... just market to enter, loop to get price and compare to stops, and place orders as needed).  This eliminates need
# to place any open limit orders, but causes delays in  responding to the stops when they are hit.
#		spy_df = _req_historical_candles(ib_contract=spy_contract, app=app)
#		spy_last = spy_df['Close'].values[-1]			# Most recent closing bar price
#		print ("SPY last  = ", spy_last)		# Count down on terminal so can watch/check
# Should be able to  request data only for SPY's last tick ... not 2 days of 5 min bars as above. But can't get this to work.
#		spy_df = app.reqMktData(1, spy_contract, '', False, False, [])
#		spy_last = spy_df['Close'].values[-1]				# Most recent closing bar price
#		print ("reqMktData: SPY last  = ", spy_last)		# Count down on terminal so can watch/check

# Gets here if fall out of main while block above (time out of range).
time.sleep(2)
fileout.close()
app.disconnect()

