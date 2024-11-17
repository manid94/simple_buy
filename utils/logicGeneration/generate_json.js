function symbolsChange() {
    const symbols = document.getElementById("symbols").value;
    const [SYMBOL, token, diff] = getSymbolDetails(symbols);
    document.getElementById("strikeDiff").setAttribute('step', diff)
    updateJSON()
}

function updateJSON() {
    // Retrieve values from input fields
    const symbols = document.getElementById("symbols").value;
    
    const [SYMBOL, token, ] = getSymbolDetails(symbols);

    const strikeDiff = parseInt(document.getElementById("strikeDiff").value, 10);
    const safetyStopLossPercentage = parseInt(document.getElementById("safetyStopLossPercentage").value, 10);
    const staticBuyBack =  document.getElementById("staticBuyBack").checked;
    const buyAtPercentage = parseInt(document.getElementById("buyAtPercentage").value, 10);
    const sellProfitPercentage = parseInt(document.getElementById("sellProfitPercentage").value, 10);
    const initialLots = parseInt(document.getElementById("initialLots").value, 10);
    const targetProfit = parseInt(document.getElementById("targetProfit").value, 10);
    const maxLoss = parseInt(document.getElementById("maxLoss").value, 10);
    const entryTime = document.getElementById("entryTime").value.split(':');
    const exitTime = document.getElementById("exitTime").value.split(':');
    const enableTrailing = document.getElementById("enableTrailing").checked;
    const profitTrailStartAt = parseInt(document.getElementById("profitTrailStartAt").value, 10);
    const profitLockAt = parseInt(document.getElementById("profitLockAt").value, 10);
    const profitTrailIncreaseAt = parseInt(document.getElementById("profitTrailIncreaseAt").value, 10);
    const profitLockIncreaseAt = parseInt(document.getElementById("profitLockIncreaseAt").value, 10);
    // Update slider display value
    document.getElementById("profitTrailValue").textContent = profitTrailStartAt;
    document.getElementById("profitLockValue").textContent = profitLockAt;
    document.getElementById("profitTrailIncreaseValue").textContent = profitTrailIncreaseAt;
    document.getElementById("profitLockIncreaseValue").textContent = profitLockIncreaseAt;
    document.getElementById("strikeDiffValue").textContent = strikeDiff;
    document.getElementById("buyAtPercentageValue").textContent = buyAtPercentage
    document.getElementById("sellProfitPercentageValue").textContent = sellProfitPercentage;
    document.getElementById("safetyStopLossPercentageValue").textContent = safetyStopLossPercentage;




    
    // Define the JSON structure
    const config = {
        'SYMBOL': SYMBOL,
        'token': token,
        'INITIAL_LOTS': initialLots,
        'STRIKE_DIFFERENCE': strikeDiff,
        'SAFETY_STOP_LOSS_PERCENTAGE': +(safetyStopLossPercentage/100).toFixed(2),
        'BUY_BACK_PERCENTAGE': +(1-(buyAtPercentage/100)).toFixed(2),
        'SELL_TARGET_PERCENTAGE': +(sellProfitPercentage/100).toFixed(2),
        'TARGET_PROFIT': targetProfit,
        'MAX_LOSS': maxLoss,
        'ENTRY_TIME': {
            'hours': +entryTime[0],
            'minutes': +entryTime[1],
            'seconds': +entryTime[2]
        },
        'EXIT_TIME': {
            'hours': +exitTime[0],
            'minutes': +exitTime[1],
            'seconds': +exitTime[2]
        },
        'BUY_BACK_STATIC': staticBuyBack,
        'BUY_BACK_LOTS': 1,
        'ENABLE_TRAILING': enableTrailing,
        'Trail_config': enableTrailing ? {
            'profit_trail_start_at': profitTrailStartAt,
            'profit_lock_after_start': profitLockAt,
            'on_profit_increase_from_trail': profitTrailIncreaseAt,
            'increase_profit_lock_by': profitLockIncreaseAt
        } : null
    };

    // Display the generated JSON
    document.getElementById("output").textContent = JSON.stringify(config, null, 4);
}

function copyJSON() {
    const jsonText = document.getElementById("output").textContent;
    navigator.clipboard.writeText(jsonText).then(() => {
        const copyMessage = document.getElementById("copyMessage");
        copyMessage.style.display = "block";
        setTimeout(() => {
            copyMessage.style.display = "none";
        }, 2000);
    });
}
function getSymbolDetails(symbols) {
    const datas = {
        bank : [
            "BANK_NIFTY", '26009', 100
    ],
        nifty : [
            "NIFTY", '26000', 50
    ]
    }
    return datas[symbols]
}
// Initial JSON load
updateJSON();