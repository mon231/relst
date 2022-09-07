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

titleElement.innerText = classInfo["name"];
authorElement.innerText = `(by ${classInfo["author"]})`;
dateElement.innerText = classInfo["date"];
descElement.innerText = classInfo["description"];

titleElement.append(authorElement);

functionsList.forEach((func) => {
	const itemElement = document.createElement('li');
	const anchorElement = document.createElement('a');
	const anchorImgElement = document.createElement('img');
	const functionElement = document.createElement('h3');
	const functionLinkElement = document.createElement('a');

	itemElement.classList.add('function-item');
	functionElement.classList.add('function-name');
	functionElement.classList.add('underline');
	anchorElement.classList.add('function-anchor');
	functionLinkElement.classList.add('function-link');

	anchorImgElement.setAttribute('src', '../images/anchor.png');
	anchorImgElement.setAttribute('width', '16');
	anchorImgElement.setAttribute('height', '16');
	itemElement.setAttribute('id', `${func}`);
	anchorElement.setAttribute('href', `#${func}`);
	functionLinkElement.setAttribute('href', '#');

	anchorElement.append(anchorImgElement);
	itemElement.append(anchorElement);
	functionElement.append(functionLinkElement);
	functionLinkElement.innerText = func;
	itemElement.append(functionElement);
	listElement.append(itemElement);
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
	return ["getTemperature", "getPrecipitation"];
}
