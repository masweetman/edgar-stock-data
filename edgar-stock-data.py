# -*- coding: utf-8 -*-

# import modules
import config
import requests
import pandas as pd
import pathlib
import time
import statistics

# request header
headers = {'User-Agent': config.email}

# get tickers and CIK numbers
time.sleep(0.11)
companyTickers = requests.get("https://www.sec.gov/files/company_tickers.json", headers=headers)
companyData = pd.DataFrame.from_dict(companyTickers.json(), orient='index')

tickers = config.tickers
years = config.years

stockData = {}

#add ticker to data
for ticker in tickers:
    edgarTicker = ticker.replace('.','-')
    if companyData[companyData['ticker'] == edgarTicker].any().iloc[0]:
        stockData[ticker] = {}
        stockData[ticker]['EPS (Avg)'] = {}
        stockData[ticker]['BVPS'] = None
        stockData[ticker]['Div'] = None
        stockData[ticker]['Div Date'] = None
        stockData[ticker]['cik'] = companyData[companyData['ticker'] == edgarTicker].cik_str.iloc[0]
    else:
        stockData[ticker] = {}
        stockData[ticker]['EPS (Avg)'] = 'Ticker not found.'
        stockData[ticker]['cik'] = None
        continue

#get annual EPS
for year in years:
    time.sleep(0.11)
    framesEpsDiluted = requests.get(f'https://data.sec.gov/api/xbrl/frames/us-gaap/EarningsPerShareDiluted/USD-per-shares/CY{year}.json', headers=headers)
    framesEpsDiluted = framesEpsDiluted.json()['data']
    framesEpsDiluted = pd.DataFrame.from_dict(framesEpsDiluted)

    for ticker in stockData:
        cik = stockData[ticker]['cik']

        if cik == None:
            continue

        if framesEpsDiluted[framesEpsDiluted['cik'] == cik]['val'].any():
            stockData[ticker]['EPS (Avg)'][year] = framesEpsDiluted[framesEpsDiluted['cik'] == cik]['val'].iloc[0]
        else:
            stockData[ticker]['EPS (Avg)'][year] = None

#get facts
for ticker in stockData:
    print(ticker)
    cik = stockData[ticker]['cik']
    
    if cik == None:
        continue
    else:
        cik = str(cik).zfill(10)
        
    time.sleep(0.11)
    facts = requests.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json', headers=headers)

    #get book value per share
    if 'Assets' in facts.json()['facts']['us-gaap']:
        assets = facts.json()['facts']['us-gaap']['Assets']['units']['USD'][-1]['val']
    
    if 'Liabilities' in facts.json()['facts']['us-gaap']:
        liabilities = facts.json()['facts']['us-gaap']['Liabilities']['units']['USD'][-1]['val']
    elif 'LiabilitiesCurrent' in facts.json()['facts']['us-gaap']:
        liabilities = facts.json()['facts']['us-gaap']['LiabilitiesCurrent']['units']['USD'][-1]['val']
        if 'LiabilitiesNoncurrent' in facts.json()['facts']['us-gaap']:
            liabilities = liabilities + facts.json()['facts']['us-gaap']['LiabilitiesNoncurrent']['units']['USD'][-1]['val']
    
    if 'WeightedAverageNumberOfSharesOutstandingBasic' in facts.json()['facts']['us-gaap']:
        shares = facts.json()['facts']['us-gaap']['WeightedAverageNumberOfSharesOutstandingBasic']['units']['shares'][-1]['val']
    elif 'CommonStockSharesOutstanding' in facts.json()['facts']['us-gaap']:
        shares = facts.json()['facts']['us-gaap']['CommonStockSharesOutstanding']['units']['shares'][-1]['val']

    if shares > 0:
        bvps = round((assets - liabilities) / shares, 2)
        stockData[ticker]['BVPS'] = bvps

    if 'CommonStockDividendsPerShareDeclared' in facts.json()['facts']['us-gaap']:
        stockData[ticker]['Div'] = facts.json()['facts']['us-gaap']['CommonStockDividendsPerShareDeclared']['units']['USD/shares'][-1]['val']
        stockData[ticker]['Div Date'] = facts.json()['facts']['us-gaap']['CommonStockDividendsPerShareDeclared']['units']['USD/shares'][-1]['end']
    
    if 'CommonStockDividendsPerShareCashPaid' in facts.json()['facts']['us-gaap']:
        stockData[ticker]['Div'] = facts.json()['facts']['us-gaap']['CommonStockDividendsPerShareCashPaid']['units']['USD/shares'][-1]['val']
        stockData[ticker]['Div Date'] = facts.json()['facts']['us-gaap']['CommonStockDividendsPerShareCashPaid']['units']['USD/shares'][-1]['end']
    
    if 'DividendsCommonStock' in facts.json()['facts']['us-gaap']:
        div = facts.json()['facts']['us-gaap']['DividendsCommonStock']['units']['USD'][-1]['val']
        stockData[ticker]['Div'] = round(div/shares, 2)
        stockData[ticker]['Div Date'] = facts.json()['facts']['us-gaap']['DividendsCommonStock']['units']['USD'][-1]['end']
    
    #calculate average EPS
    eps = list(stockData[ticker]['EPS (Avg)'].values())
    eps = [x for x in eps if x is not None]
    if len(eps) > 0:
        stockData[ticker]['EPS (Avg)'] = round(statistics.mean(eps), 2)
    else:
        stockData[ticker]['EPS (Avg)'] = None

stockData = pd.DataFrame.from_dict(stockData).transpose()

#export to csv
path = pathlib.Path(__file__).parent.resolve()
stockData.to_csv(path/'stockdata.csv')
