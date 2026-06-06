/** Mapeia um nome de modelo a uma família, com letra e cor para o badge
 *  (à falta de logos de marca, um badge minimalista colorido por família). */
export function modelFamily(name: string): { label: string; color: string } {
	const n = (name || '').toLowerCase();
	if (n.includes('qwen')) return { label: 'Q', color: '#a78bfa' };
	if (n.includes('gemma')) return { label: 'G', color: '#60a5fa' };
	if (n.includes('deepseek')) return { label: 'D', color: '#34d399' };
	if (n.includes('llama')) return { label: 'L', color: '#f59e0b' };
	if (n.includes('mistral') || n.includes('mixtral')) return { label: 'M', color: '#fb7185' };
	if (n.includes('phi')) return { label: 'φ', color: '#22d3ee' };
	if (n.includes('embed')) return { label: 'E', color: '#9ca3af' };
	return { label: '◆', color: '#9cdef2' };
}
