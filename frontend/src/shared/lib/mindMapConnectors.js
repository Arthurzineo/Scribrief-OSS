/** Measure the displayed tree so SVG lines never cross cards or imply card-to-card links. */
export function measureMindMapConnectors(canvas) {
  const center = canvas.querySelector('.mind-map__center');
  const branches = [...canvas.querySelectorAll('.mind-map__branch')];
  if (!center || !branches.length) return null;

  const box = canvas.getBoundingClientRect();
  const centerBox = center.getBoundingClientRect();
  const titleBoxes = branches.map((branch) =>
    branch.querySelector('.mind-map__branch-title').getBoundingClientRect());
  const leftTitles = titleBoxes.filter((_, index) => index % 2 === 0);
  const rightTitles = titleBoxes.filter((_, index) => index % 2 === 1);
  const railLeft = Math.min(...leftTitles.map((title) => title.left - box.left)) - 12;
  const railRight = rightTitles.length
    ? Math.max(...rightTitles.map((title) => title.right - box.left)) + 12
    : null;
  const links = titleBoxes.map((title, index) => {
    const y = title.top + title.height / 2 - box.top;
    return index % 2 === 0
      ? { id: index, x1: railLeft, x2: title.left - box.left, y }
      : { id: index, x1: title.right - box.left, x2: railRight, y };
  });
  const children = branches.map((branch, index) => {
    const title = titleBoxes[index];
    const leftSide = index % 2 === 0;
    const spineX = (leftSide ? title.left + 16 : title.right - 16) - box.left;
    const cardLinks = [...branch.querySelectorAll('.mind-map__card')].map((card, pointIndex) => {
      const rect = card.getBoundingClientRect();
      const y = rect.top + rect.height / 2 - box.top;
      return leftSide
        ? { id: `${index}-${pointIndex}`, x1: spineX, x2: rect.left - box.left, y }
        : { id: `${index}-${pointIndex}`, x1: rect.right - box.left, x2: spineX, y };
    });
    return {
      id: index, spineX, top: title.bottom - box.top,
      bottom: cardLinks.at(-1)?.y ?? title.bottom - box.top,
      links: cardLinks,
    };
  });
  return {
    width: box.width, height: box.height,
    rootX: centerBox.left + centerBox.width / 2 - box.left,
    rootBottom: centerBox.bottom - box.top,
    trunkY: Math.min(...titleBoxes.map((title) => title.top - box.top)) - 24,
    railLeft, railRight,
    leftEnd: Math.max(...links.filter((link) => link.id % 2 === 0).map((link) => link.y)),
    rightEnd: rightTitles.length
      ? Math.max(...links.filter((link) => link.id % 2 === 1).map((link) => link.y))
      : null,
    links, children,
  };
}
