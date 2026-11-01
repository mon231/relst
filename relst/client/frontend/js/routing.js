const PAGE_PARAMS = 'json_params';

/**
 * @brief The function routes to another page
 * @param {string} url - page url to route to 
 * @param {Object} params - post params to dest page 
 */
function routeToPage(url, params) {
	const formElement = document.createElement('form');
	const dataElement = document.createElement('input');

	formElement.action = url;
	formElement.method = 'get';
	formElement.style.display = 'none';

	dataElement.type = 'hidden';
	dataElement.value = JSON.stringify(params);
	dataElement.name = dataElement.id = PAGE_PARAMS;

	formElement.append(dataElement);
	document.body.append(formElement);

	formElement.submit();
}

function getPageParams() {
	const urlParams = new URLSearchParams(window.location.search);
	return urlParams.get(PAGE_PARAMS);
}
