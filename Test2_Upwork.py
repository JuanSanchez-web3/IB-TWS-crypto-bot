# This Python program is a template for an automated trading strategy at IB that uses the IB API.
# It uses a simple EMA5 moving average and 5-min SPY bars.  If close of a 5-min bar is above the
# prior bar's EMA value, and have no position, then go long. Reverse for short. Exits are based on
# profit ans loss stops placed as a bracket order wuth the initial entry.  Much of the core code is
# here, and a function for a bracket order was pasted in below from IB's website. 
# Randy May. Last updated 8/17/24.

import sys
import pandas as pd
import time
import numpy as np
import logging
import threading
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import *
from datetime import date, datetime, timedelta
from pytz import timezone
from pyti.hull_moving_average import hull_moving_average as hma
from pyti.exponential_moving_average import exponential_moving_average as ema
from decimal import Decimal
import csv

ib_event = threading.Event()
ib_event.clear()

fillprice = 1.0			# Declare here so it is global?
iposition = 0           # Use to flag long (1), short (-1), or no position (0)
# Adjust parameters below as needed for 5-min SPY bars
EMA_length = 5			# EMA length for trades
Profit_stop = 1.0		# Placeholder until assigned actual SPY price
Stop_loss = 1.0			# Ditto (declared here so global?)
profit_offset = 4.0		# Offset for profit stop SPY price for orders
stop_offset = 1.0		# Ditto for stop losses
limitPrice = 1.0		# Variables for bracket order try
takeProfitLimitPrice = 1.0
stopLossPrice = 1.0
order_messages = []  # To store parsed order messages [orderId, action, type, quantity, lastFillPrice, orderStatus]
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
		global order_messages
		for order_message in order_messages:
			if order_message['orderId'] == orderId:
				order_message['lastFillPrice'] = lastFillPrice
		#global fillprice
		print('orderStatus - orderid:', orderId, 'status:', status, 'filled', filled, 'remaining', remaining, 'lastFillPrice', lastFillPrice)
	
	def openOrder(self, orderId, contract, order, orderState):
		global order_messages
		if not order_messages:
			new_order = {
				'orderId': orderId,
				'action': order.action,
				'type': order.orderType,
				'quantity': order.totalQuantity,
				'orderStatus': orderState.status
			}
			order_messages.append(new_order)
		else:
			# If there are orders, check for orderId 3
			order_exists = any(order_message['orderId'] == orderId for order_message in order_messages)
			if not order_exists:
				new_order = {
					'orderId': orderId,
					'action': order.action,
					'type': order.orderType,
					'quantity': order.totalQuantity,
					'orderStatus': orderState.status
				}
				order_messages.append(new_order)
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
		print('In execDetails:', tempstring)
		print('fillprice = ', str(fillprice))
		fileout.write(tempstring)
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
			qqq_snapshot = price
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
#		self._place_order(symbol=symbol, position_size=position_size, action='BUY',orderType='MKT')			# Doesn't work
		iposition = 1
		print("Placed order to BUY " + str(position_size) + " shares of " + symbol)
		print("In go_long: iposition = " + str(iposition) + "\n")

	def go_short(self, symbol, position_size):
		global iposition
		self._place_order(symbol=symbol, position_size=position_size, action='SELL')
#		self._place_order(symbol=symbol, position_size=position_size, action='SELL', orderType='MKT')		# Doesn't work
		iposition = -1
		print("Placed order to SELL " + str(position_size) + " shares of " + symbol)
		print("In go_short: iposition = " + str(iposition) + "\n")

# Below was modified to try and pass the orderType as a parameter so that it could be set to either MKT or LMT, but
# although there were no syntax errors, IB returns an error that it doesn't recognize the order type. So apparently
# whatever I'm passing in doesn't work. Also  must send in the limit price for a limit order, so that would also need
# to be added to the parameter list somehow.
#	def _place_order(self, symbol, position_size, action, orderType):		# Doesn't like orderType added
	def _place_order(self, symbol, position_size, action):
		contract = Contract()
		contract.symbol = symbol
		contract.secType = "STK"
		contract.exchange = "SMART"
		contract.currency = "USD"
		order = Order()
		order.action = action
#		order.lmtPrice = limitPrice		    # How to get this passed to the function?
#		order.orderType = "LMT"				# How to get this passed to the function?
		order.orderType = "MKT"				# Tried passing to this function (didn't work)
		order.totalQuantity = position_size
# 8/20/24, R.May. Added 2 lines below from website forum that suggested it.
		order.eTradeOnly = False
		order.firmQuoteOnly = False
		order.transmit = True

		self.nextorderId +=1
		self.placeOrder(orderId=self.nextorderId, contract=contract, order=order)

		return order
	
# Added functions below in attempt for bracket orders. Not working for multiple problems with variables being passed/used.
# At bottom: have app.go_bracket_long(symbol='SPY', position_size=cnt_spy, limitPrice=spy_last+0.1,takeProfitLimitPrice=Profit_stop, stopLossPrice=Stop_loss)
	def go_bracket_long(self, symbol, position_size, limitPrice, takeProfitLimitPrice, stopLossPrice):		# Attempt at bracket order
		global iposition
		order_id = self.nextValidId
		bracket = BracketOrder(order_id, "BUY", position_size, limitPrice,takeProfitLimitPrice,stopLossPrice)
#		self.BracketOrder(symbol=symbol, action='BUY',position_size=position_size, limitPrice=limitPrice, takeProfitPrice=takeProfitLimitPrice, stopLossPrice=stopLossPrice)
		iposition = 1

# Next 3 lines are from a web example on reddit (link below), where I replaced "app" with "self":
# https://www.reddit.com/r/interactivebrokers/comments/pxnmvo/ib_api_python_bracket_order/
		for o in bracket:
			self._place_order(symbol=symbol, position_size=position_size, action='BUY', orderType='LMT')
#			self._place_order(o.orderID, symbol=symbol, position_size=position_size, action='BUY', orderType='LMT', o)    # Doesn't like the "o" here
#    		self.nextValidOrderId		# This causes a problem

		print("Placed bracket order to BUY " + str(position_size) + "shares of " + symbol)
		print("In go_bracket_long: iposition = " + str(iposition) + "\n")
		print("In go_bracket_long: limitPrice = " + str(limitPrice) + "\n")
		print("In go_bracket_long: takeProfitLimitPrice = " + str(takeProfitLimitPrice) + "\n")
		print("In go_bracket_long: stopLossPrice = " + str(stopLossPrice) + "\n")

	def go_bracket_short(self, symbol, position_size, limitPrice, takeProfitLimitPrice,stopLossPrice):		# Add limit, profit and stop prices
		global iposition
		order_id = self.nextValidId
		bracket = BracketOrder(order_id, "SELL", position_size, limitPrice,takeProfitLimitPrice,stopLossPrice)
#		self.BracketOrder(symbol=symbol, action='SELL',position_size=position_size, limitPrice=limitPrice, takeProfitPrice=takeProfitLimitPrice, stopLossPrice=stopLossPrice)
		iposition = -1
# Next lines are from a web example on reddit (link below), where I replaced "app" with "self":
# https://www.reddit.com/r/interactivebrokers/comments/pxnmvo/ib_api_python_bracket_order/
# This fails with an error (related to "o") that "positional argument follows keyword argument".  What is "o" and
# where is is defined?
		for o in bracket:
			self._place_order(symbol=symbol, position_size=position_size, action='BUY', orderType='LMT')
#			self._place_order(o.orderID, symbol=symbol, position_size=position_size, action='SELL', orderType='LMT', o)    # Doesn't like the "o" here
#    		self.nextValidOrderId		# This causes a problem

		print("Placed bracket order to SELL " + str(position_size) + "shares of " + symbol)
		print("In go_bracket_short: iposition = " + str(iposition) + "\n")
		print("In go_bracket_short: limitPrice = " + str(limitPrice) + "\n")
		print("In go_bracket_short: takeProfitLimitPrice = " + str(takeProfitLimitPrice) + "\n")
		print("In go_bracket_short: stoplossPrice = " + str(stopLossPrice) + "\n")

# Below is a paste from IB website giving Python example of a bracket order. Not clear how to get parameters to
# this function, or how to loop over the "o" structure in the calling code.

#@staticmethod
def BracketOrder(parentOrderId:int, action:str, quantity:Decimal, 
                 limitPrice:float, takeProfitLimitPrice:float, 
                 stopLossPrice:float):
     
# This will be the main or "parent" order
	parent = Order()
	parent.orderId = parentOrderId
	parent.action = action
	parent.orderType = "LMT"
	parent.totalQuantity = quantity
	parent.lmtPrice = limitPrice
# The parent and children orders will need this attribute set to False to prevent accidental executions.
# The LAST CHILD will have it set to True, 
	parent.transmit = False
 
	takeProfit = Order()
	takeProfit.orderId = parent.orderId + 1
	takeProfit.action = "SELL" if action == "BUY" else "BUY"
	takeProfit.orderType = "LMT"
	takeProfit.totalQuantity = quantity
	takeProfit.lmtPrice = takeProfitLimitPrice
	takeProfit.parentId = parentOrderId
	takeProfit.transmit = False
 
	stopLoss = Order()
	stopLoss.orderId = parent.orderId + 2
	stopLoss.action = "SELL" if action == "BUY" else "BUY"
	stopLoss.orderType = "STP"
#Stop trigger price
	stopLoss.auxPrice = stopLossPrice
	stopLoss.totalQuantity = quantity
	stopLoss.parentId = parentOrderId
#In this case, the low side order will be the last child being sent. Therefore, it needs to set this attribute to True 
#to activate all its predecessors
	stopLoss.transmit = True
 
	bracketOrder = [parent, takeProfit, stopLoss]
	return bracketOrder

# Below is part of example from the IB TWS documentation.  Not sure what "o" is or where it is defined

#bracket = OrderSamples.BracketOrder(self.nextOrderId(), "BUY", 100, 30, 40, 20)
#for o in bracket:
#  self.placeOrder(o.orderId, ContractSamples.EuropeanStock(), o)
#  self.nextOrderId()  # need to advance this we'll skip one extra order id, it's fine


def run_loop():
	app.run()			

app = IBapi()
app.ib_connect(host='127.0.0.1', port=7497, clientId=127, account='1')			# Is port 7497 for paper trading?  What about account entry?
#app.ib_connect(host='127.0.0.1', port=7496, clientId=127, account='xxxxxx')		# Removed account number as this is live

#Start the socket in a thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

time.sleep(2)    # Sleep interval to allow time for connection to the server

# Define the number of shares of SPY to trade (use 20 for testing)
cnt_spy = 20			# SPY
#cnt_mes = 1				# MES futures (for later)
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

print ("Starting test ...\n")
fileout.write ("Started test program\n")

# Get the current NY time after initializing some variables
NYhour = 0				# Initialize this to zero to start
hour = 0				# Ditto
minute = 0				# Ditto
startflag = 0			# Flag that start of trading has not yet begun
combined_hs = 0			# Variable to hold a time value like 941, 1553, etc.
t_start = 930			# 9:30 am New York time
t_end = 1600			# 4:00 pm Hew York time
min_bars = 5			# Trades on 5 minute bars
updateflag = 0			# Flag that a new 5-minute update is needed

# Note: This program is assumed to have been started shortly before market open and is manually closed after
# market close.  So no need to poll for 9:30am ... just bracket the order placement process for regular hours.
# For new  5-min SPY, first valid EMA bar is bar that closes at 9:50am (935, 940, 945 are first 3, and scheme
# uses current bar close > EMA5 for PRIOR bar). So start program manually at about 9:47am.
now = datetime.now()			# Current date and time
year = now.strftime("%Y")
month = now.strftime("%m")
day = now.strftime("%d")
hour = now.strftime("%H")		# 24-hr format, but local time in Tucson, AZ
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

# For this test program, start with simple buy and sell of 100 SPY contracts in paper account (which has
# username wingfppt9, password carnoustie88).  If this works, expand to try a bracket order, or else
# a market entry with immediate profit and loss stop limit orders, OCO.
spy_last = spy_df['Close'].values[-1]			# Most recent closing bar price
ema_last = ema_spy[-2]			# Prior bar (-1 is current value)
Profitstop = spy_last + 4.0		# For testing long only bracket order entry
Srop_loss = spy_last - 1.0
print("spy_last = $", spy_last)
print("ema_last = $", ema_last)
print("Profit_stop = $", Profit_stop)
print("Stop_loss = $", Stop_loss)
fileout.write("SPY last = " + str(spy_last))
fileout.write("EMA last = " + str(ema_last))
fileout.write("\n")

app.account_updates()			# Updata account data

spy_current_pos = app.portfolio['SPY']['position'] if 'SPY' in app.portfolio.keys() else 0
print("SPY current position is: ", spy_current_pos)
fileout.write("SPY current positions is = " + str(spy_current_pos))
fileout.write("\n")
spy_avgCost = app.portfolio['SPY']['averageCost'] if 'SPY' in app.portfolio.keys() else 0
print("SPY average cost is: ", spy_avgCost)
fileout.write("SPY average cost = " + str(spy_avgCost))
fileout.write("\n")
print ("Finished account download\n")

print("Placing order to buy 20 SPY at market\n")
fileout.write("Placing order for 20 SPY\n")
app.go_long(symbol='SPY', position_size=cnt_spy)		# New long entry
print("New long, fillprice = $", fillprice)

time.sleep(10)				# Delay 10s before exiting the trade

print("Placing order to sell 20 SPY at market\n")
fileout.write("Placing order for 20 SPY\n")
app.go_short(symbol='SPY', position_size=cnt_spy)		# New long entry
print("Exiting SPY, fillprice = $", fillprice)

time.sleep(10)				# Delay 30s


fileout.close()

csv_file = 'orders.csv'
with open(csv_file, mode='w', newline='') as file:
    writer = csv.DictWriter(file, fieldnames=order_messages[0].keys())
    writer.writeheader()  # Write the header
    writer.writerows(order_messages)  # Write the data

print(f"\nOrders saved to {csv_file}")
# End program
time.sleep(2)
#fileout.close()
app.disconnect()

