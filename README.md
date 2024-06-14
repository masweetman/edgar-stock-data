# edgar-stock-data

A very simple python script to get a few bits of data from sec.gov.

# What I do

I use the sec.gov API (https://www.sec.gov/edgar/sec-api-documentation) to collect EPS, BVPS, and Dividends and put them in a CSV file. Sometimes I get things wrong, but I hope to improve:
- I look for earnings per share from previous years and calculate average annual earnings per share (EPS)
- I try to find assets, liabilities, and number of shares outstanding and use them to calculate book value per share (BVPS)
- I scour the database for the most recent dividend

# Getting started

Replicate config_example.py to config.py and configure a few bits of info in config.py:
- Enter your email address to declare your user agent in the request header. Refer to https://www.sec.gov/os/webmaster-faq#developers
- Enter an array of ticker symbols.
- Enter an array of years.
- Run edgar-stock-data.py
- I'll create stockdata.csv. Open it to see what I found!