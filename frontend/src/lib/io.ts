/** Descarrega dados como ficheiro JSON. */
export function downloadJson(filename: string, data: unknown) {
	const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = filename;
	a.click();
	URL.revokeObjectURL(url);
}

/** Abre o seletor de ficheiros e devolve o JSON parseado (ou rejeita). */
export function pickJsonFile(): Promise<unknown> {
	return new Promise((resolve, reject) => {
		const inp = document.createElement('input');
		inp.type = 'file';
		inp.accept = 'application/json,.json';
		inp.onchange = () => {
			const f = inp.files?.[0];
			if (!f) return reject(new Error('sem ficheiro'));
			const r = new FileReader();
			r.onload = () => {
				try {
					resolve(JSON.parse(r.result as string));
				} catch (e) {
					reject(e);
				}
			};
			r.onerror = () => reject(r.error);
			r.readAsText(f);
		};
		inp.click();
	});
}
