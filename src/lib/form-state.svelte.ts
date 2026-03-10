let visible = $state(false);

export const formState = {
	get visible() {
		return visible;
	},
	open() {
		visible = true;
	},
	close() {
		visible = false;
	}
};
