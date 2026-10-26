/** Non-overlapping polling. Disposal suppresses late results and future requests. */
export function poll<T>(
  load: () => Promise<T>,
  receive: (value: T) => void,
  fail: (error: unknown) => void,
  delay: number,
  keepPolling: (value: T) => boolean = () => true,
) {
  let disposed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  async function tick() {
    let again = true;
    try {
      const result = await load();
      if (disposed) return;
      receive(result);
      again = keepPolling(result);
    } catch (error) {
      if (!disposed) fail(error);
    }
    if (!disposed && again) timer = setTimeout(tick, delay);
  }
  void tick();
  return () => {
    disposed = true;
    if (timer) clearTimeout(timer);
  };
}
