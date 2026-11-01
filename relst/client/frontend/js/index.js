const titleElement = document.createElement('h1');
const authorElement = document.createElement('span');
const dateElement = document.createElement('p');
const descElement = document.createElement('p');
const listElement = document.createElement('ul');
const wrapper = document.querySelector('.wrapper');
const classInfo = getClassInfo();
const functionsList = getFunctionsList();

titleElement.classList.add('class-title');
authorElement.classList.add('class-author');
dateElement.classList.add('class-date');
descElement.classList.add('class-info');
listElement.classList.add('functions-list');

titleElement.innerText = classInfo['name'];
authorElement.innerText = `(by ${classInfo['author']})`;
dateElement.innerText = classInfo['date'];
descElement.innerText = classInfo['description'];

titleElement.append(authorElement);

functionsList.forEach((func) => {
	const itemElement = document.createElement('li');
	const headlineElement = document.createElement('div');
	const anchorElement = document.createElement('a');
	const anchorImgElement = document.createElement('img');
	const nameElement = document.createElement('p');
	const linkElement = document.createElement('a');
	const briefElement = document.createElement('p');
	const hrElement = document.createElement('hr');

	itemElement.classList.add('function-item');
	nameElement.classList.add('function-name');
	nameElement.classList.add('underline');
	headlineElement.classList.add('function-headline');
	anchorElement.classList.add('function-anchor');
	linkElement.classList.add('function-link');
	briefElement.classList.add('function-brief');
	hrElement.classList.add('line-separator');

	anchorImgElement.setAttribute('src', '../images/anchor.png');
	anchorImgElement.setAttribute('width', '10');
	anchorImgElement.setAttribute('height', '10');
	itemElement.setAttribute('id', `${func['name']}`);
	anchorElement.setAttribute('href', `#${func['name']}`);
	anchorElement.setAttribute('title', 'Permalink to this headline');
	linkElement.setAttribute('href', '#');

	headlineElement.append(anchorElement);
	anchorElement.append(anchorImgElement);
	nameElement.append(linkElement);

	linkElement.innerText = parseFunction(func);
	headlineElement.append(nameElement);
	briefElement.innerText = func['brief'];
	itemElement.append(headlineElement);
	itemElement.append(briefElement);
	listElement.append(itemElement);
	listElement.append(hrElement);
});

wrapper.append(titleElement);
wrapper.append(dateElement);
wrapper.append(descElement);
wrapper.append(listElement);

function getClassInfo() {
	return {
		"name": "Weather",
		"description": "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
		"author": "Nissim Malka",
		"date": "25 July 2022"
	};
}

function getFunctionsList() {
	return [
		{
			name: "getTemperature",
			brief: "Returns the current temparature in a given country",
			params: [{"name": "country", "type": "str"}],
			return: {"name": "temparature", "type": "float"}
		}, {
			name: "getPrecipitation",
			brief: "Returns the current precipitation percentage in a given country",
			params: [{"name": "country", "type": "str"}],
			return: {"name": "precipitation", "type": "float"}
		}	
	];
}

function parseFunction(func) {
	const params = func['params'];

	const paramsParsed = params.map((param) => {
		return `${param['name']}: ${param['type']}`;
	}).join(', ');

	return `${func['name']}(${paramsParsed}) -> ${func['return']['type']}`;
}