import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TrendChart } from '../components/charts';

function plot(values: number[]) {
  return render(<TrendChart points={values.map((pct, i) => ({ pct, label: `Assignment ${i + 1}`, short: `A${i + 1}` }))} />);
}

function finiteCoordinates(container: HTMLElement) {
  const svg = container.querySelector('svg')!;
  expect(svg.outerHTML).not.toMatch(/NaN|Infinity/);
  for (const node of svg.querySelectorAll('circle, line, text')) {
    for (const attribute of ['cx', 'cy', 'x', 'y', 'x1', 'x2', 'y1', 'y2']) {
      const value = node.getAttribute(attribute);
      if (value !== null) expect(Number.isFinite(Number(value)), `${node.tagName}.${attribute}`).toBe(true);
    }
  }
  expect(svg.querySelectorAll('.grid-line').length).toBeLessThanOrEqual(12);
  for (const point of svg.querySelectorAll('circle')) {
    expect(Number(point.getAttribute('cy'))).toBeGreaterThanOrEqual(12);
    expect(Number(point.getAttribute('cy'))).toBeLessThanOrEqual(162);
  }
}

describe('TrendChart numeric ranges', () => {
  it('keeps ordinary ticks, path and point coordinates unchanged', () => {
    const { container } = plot([60, 100]);
    expect([...container.querySelectorAll('g text')].map((t) => t.textContent)).toEqual(['60%', '70%', '80%', '90%', '100%']);
    expect(container.querySelector('path')?.getAttribute('d')).toBe('M34.0,162.0 L408.0,12.0');
    finiteCoordinates(container);
  });

  it('keeps ordinary extra-credit ticks and truthful point detail', () => {
    const { container } = plot([80, 125]);
    expect([...container.querySelectorAll('g text')].map((t) => t.textContent)).toEqual(['60%', '80%', '100%', '120%']);
    expect(screen.getByRole('group', { name: 'Score trend across 2 assignments, latest 125%' })).toBeInTheDocument();
    const earlier = screen.getByRole('img', { name: 'Assignment 1: 80%' });
    fireEvent.focus(earlier);
    expect(container.querySelector('figcaption')?.textContent).toContain('Assignment 1');
    expect(container.querySelector('figcaption')?.textContent).toContain('80%');
    expect(earlier).toHaveAttribute('r', '6');
    fireEvent.blur(earlier);
    expect(container.querySelector('figcaption')?.textContent).toContain('Assignment 2');
    expect(container.querySelector('figcaption')?.textContent).toContain('125%');
    expect(earlier).toHaveAttribute('r', '4.5');
    finiteCoordinates(container);
  });

  it.each([
    [80, 1e308],
    [-1e308, 1e308],
    [-Number.MAX_VALUE, Number.MAX_VALUE],
    [0, Number.MAX_VALUE],
    [-Number.MAX_VALUE, -1e308],
  ])('renders finite coordinates and bounded ticks for %j', (first, last) => {
    const { container } = plot([first, last]);
    finiteCoordinates(container);
    expect(container.querySelectorAll('.grid-line')).toHaveLength(12);
    expect(screen.getByRole('img', { name: `Assignment 2: ${Math.round(last)}%` })).toBeInTheDocument();
    expect(container.querySelector('figcaption')?.textContent).toContain(`${Math.round(last)}%`);
  });
});
