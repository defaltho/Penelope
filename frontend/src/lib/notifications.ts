export function isSupported(): boolean {
	return typeof window !== 'undefined' && 'Notification' in window;
}

export async function requestPermission(): Promise<boolean> {
	if (!isSupported()) return false;
	if (Notification.permission === 'granted') return true;
	if (Notification.permission === 'denied') return false;
	const result = await Notification.requestPermission();
	return result === 'granted';
}

export function notify(title: string, body: string, opts?: { onclick?: () => void }) {
	if (!isSupported() || Notification.permission !== 'granted') return;
	if (!document.hidden) return;
	const n = new Notification(title, { body });
	n.onclick = () => {
		window.focus();
		opts?.onclick?.();
		n.close();
	};
}
