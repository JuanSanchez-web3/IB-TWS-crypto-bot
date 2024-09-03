# Initial orders list
orders = []

# # New orders to be added as dictionaries
# newOrder1 = {
#     'orderId': 1,
#     'type': 'buy',
#     'quantity': 100,
#     'lastFillPrice': 50.25,
#     'orderStatus': 'completed'
# }

# newOrder2 = {
#     'orderId': 2,
#     'type': 'sell',
#     'quantity': 200,
#     'lastFillPrice': 75.50,
#     'orderStatus': 'pending'
# }

# # Adding new orders to the orders list
# orders.append(newOrder1)
# orders.append(newOrder2)

# New value to add (e.g., adding 'customerId')
new_value = 'cust123'

# Updating the order with orderId 1
for order in orders:
    if order:
        print("Yes")
    else:
        print("No")
    if order['orderId'] !=3:
        print(True)
        order['customerId'] = new_value
    else:
        print(False)

# Printing the updated orders list
print(orders)
