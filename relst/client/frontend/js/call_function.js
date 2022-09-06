const STRING_TYPE = 'string';

function getFunctionname() {
    return 'function_name'
}

function parseParameters() {
    // TODO: get params from request.post
}

function executeCommand(commandName, params) {
    // NOTE: THIS IS NOT IMPLEMENTED HERE
    return {
        "type": STRING_TYPE,
        "value": "nissim malka"
    }
}



////////////////////////////////////////////////////////////////
params = parseParameters();
functionName = getFunctionname();
execCommand = executeCommand(functionName, params);

// if localStorage[functionName] is undefined then localStorage[functionName] = object()
// localStorage[functionName][DataTransfer.now()] = execCommand

////////////////////////////////////////////////////////////////