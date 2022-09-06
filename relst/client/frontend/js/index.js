const ul = document.createElement('ul');
const wrapper = document.querySelector('.wrapper');
const functionsList = getFunctionsList();

ul.classList.add('functions-list');

functionsList.forEach((func) => {
	const li = document.createElement('li');
	li.classList.add('function-item');
	li.innerText = func;
	ul.append(li);
});

wrapper.append(ul);

function getFunctionsList() {
	return ["Nissim", "Malka"];
}