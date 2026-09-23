/**
 * Programs offered in the "New file" dialog.
 *
 * The sources are kept as real `.pasp` files next to this one and imported
 * with Vite's `?raw`, rather than embedded as string literals. That keeps
 * them readable, syntax-highlighted in an editor, and diffable against the
 * upstream `examples/` directory of the dPASP repository they came from.
 */

import earthquake from './earthquake.pasp?raw';
import coloring from './coloring.pasp?raw';
import insomnia from './insomnia.pasp?raw';
import prisoners from './prisoners.pasp?raw';
import argumentation from './argumentation.pasp?raw';
import learning from './learning.pasp?raw';
import poisson from './poisson.pasp?raw';
import digitsum from './digitsum.pasp?raw';

export interface Example {
  /** Stable key, used as the `<select>` value. */
  id: string;
  /** Shown in the dropdown. */
  label: string;
  /** Pre-filled into the filename box. */
  filename: string;
  /** One line on what the program demonstrates. */
  description: string;
  /**
   * Shown as a warning when selected. Set only where running the program in
   * the playground is not straightforward.
   */
  note?: string;
  code: string;
}

export const EXAMPLES: Example[] = [
  {
    id: 'earthquake',
    label: 'Earthquake — conditional queries',
    filename: 'earthquake.pasp',
    description:
      'Probabilistic facts and rules with conditional queries. Example 5 of Cozman & Mauá (JAIR 2017).',
    code: earthquake
  },
  {
    id: 'insomnia',
    label: 'Insomnia — credal bounds',
    filename: 'insomnia.pasp',
    description:
      'The smallest program with genuinely non-degenerate credal bounds: two stable models make ℙ(work) an interval. Add #semantics maxent. to see the same program collapse to a single value.',
    code: insomnia
  },
  {
    id: 'coloring',
    label: 'Graph 3-colouring — L-stable semantics',
    filename: 'coloring.pasp',
    description:
      'A random graph and its 3-colourings, under the L-stable semantics. Shows undef queries, which ask about atoms that are undefined rather than true or false.',
    code: coloring
  },
  {
    id: 'prisoners',
    label: 'Three prisoners — credal facts',
    filename: 'prisoners.pasp',
    description:
      'Interval-valued (credal) facts, written [0.475, 0.525]::a, applied to the three-prisoners paradox. Cozman & Mauá (IJAR 2017).',
    code: prisoners
  },
  {
    id: 'argumentation',
    label: 'Argumentation — attack and support',
    filename: 'argumentation.pasp',
    description:
      'Probabilistic arguments that attack and support one another: an argument holds when something positive supports it and nothing negative defeats it. Both halves of the semantics are declared, one directive each. Example 6 of Totis, De Raedt & Kimmig (2023); Example 11 of Geh et al. (2024).',
    code: argumentation
  },
  {
    id: 'learning',
    label: 'Parameter learning from a CSV',
    filename: 'learning.pasp',
    description:
      'Fits a learnable probability, written ?::burglary, to observed data with #learn. Learns from a CSV of Bert and Ernie\u2019s calls; \u2119(burglary) converges to about 0.2. From the dPASP tutorial.',
    note:
      'As written it reads the CSV from a URL, which happens while the program is parsed \u2014 so it needs outbound network from the runner. The comments in the program explain how to upload your own copy instead, which is the more reliable route. Takes roughly 15 seconds.',
    code: learning
  },
  {
    id: 'poisson',
    label: 'Poisson disasters — a PyTorch distribution',
    filename: 'poisson.pasp',
    description:
      'PyTorch inside a program: a `#python` block defines a Poisson module with a learnable rate, and a neural annotated disjunction `!::event(X) as @Poisson` turns its output into the probability of an event. Shows how a torch model supplies probabilities that ordinary rules then reason over. Examples 5 and 6 of Geh et al. (2024).',
    code: poisson
  },
  {
    id: 'digitsum',
    label: 'MNIST digit sum — neural + learning',
    filename: 'digitsum.pasp',
    description:
      'Neuro-symbolic learning: a convolutional network classifies MNIST digits while the logic program constrains their sum. Shows #python blocks, neural rules and #learn.',
    note:
      'This one downloads the MNIST dataset and trains a network. The per-run limit is 5 minutes, which the first run will probably exceed because it has to fetch MNIST; if it reports a timeout, raise DPASP_RUN_TIMEOUT (in a .env file next to compose.yaml) and try again.',
    code: digitsum
  }
];

/** Look an example up by its id. */
export function findExample(id: string): Example | undefined {
  return EXAMPLES.find((example) => example.id === id);
}
