import networkx as nx
import numpy as np
from networkx import Graph
from qiskit import Aer, execute, BasicAer

import cvxpy as cp
from itertools import product
from scipy.linalg import sqrtm


# Value of a given cut
cutValueDict = {}
def cut_value(G: Graph, x) -> int:
  #val = cutValueDict.get(x)
  #if val is not None:
  #  return val
  result = 0
  if isinstance(x, str):
    # reverse the string since qbit 0 is LSB
    x = x[::-1]  
  for edge in G.edges():
    u, v = edge
    #weight = G.get_edge_data(u,v, 'weight')['weight']
    if x[u] != x[v]: 
      result += 1 #weight
  #cutValueDict[x] = result
  return result

def value_of_edge(G: Graph, x: str, edge) -> int:
    """
    Return 1 if the edge is cut given the cut x, 0 otherwise
    """
    x = x[::-1]  # reverse x
    u, v = edge
    if x[u] != x[v] and edge in G.edges() :
      return G[u][v]['weight'] if 'weight' in G[u][v] else 1
    else:
      return 0


def get_energy(G, qaoa_qc, gamma, beta, edge, sim=Aer.get_backend('statevector_simulator'), shots=1):
  """
  Calculates the energy for a qaoa instance with the given parameters.
  This corresponds to the expected MaxCut value.
  qaoa_qc has generic Parameter() that needs to be assigned.
  """
  # prepare circuit
  qaoa_instance = qaoa_qc.assign_parameters([beta, gamma])
  if str(sim) != 'statevector_simulator':
    qaoa_instance.measure_all()

  #execute circuit
  result = execute(qaoa_instance, sim, shots=shots).result()

  #calculate energy
  energy = 0
  for cut, prob in result.get_counts().items():
    if edge is not None:
      energy += value_of_edge(G, cut, edge) * prob  #energy of single edge
    else:
      energy += cut_value(G, cut) * prob  #energy of whole graph
    
    # normalize
  if str(sim) != 'statevector_simulator':
    energy = energy / shots

  return energy


def get_energy_grid(G, qaoa_qc, edge, gammaMax=2*np.pi, betaMax=np.pi, samples=100):
  """  Calculate the energies for a 2D parameter space.  """
  gammas, betas = np.mgrid[0:gammaMax:gammaMax/samples, 0:betaMax:betaMax/samples]
  result = np.empty((samples,samples))

  print('Calculating energy:')
  for i in range(samples):
    for j in range(samples):
      result[i,j] = get_energy(G, qaoa_qc, gammas[i,j], betas[i,j], edge)

      # progress bar
      bar_len = 60
      progress = int(bar_len*(i*samples + j)/(samples**2)) + 1
      print('\r{0}{1}'.format('\u2588' * progress, '\u2591' * (bar_len-progress)), end='')
      print('\t' + f'{(i*samples + j + 1)}/{samples**2} samples', end='')
  print()
  return result


def maximizing_parameters(energy_grid, gammaMax=2*np.pi, betaMax=np.pi, plotting=True, atol=1e-5):
  """
  returns the position of the maximizing parameters.
  Used for plotting (half a pixel is added).
  For true maximizing parameters set plotting to False.
  """
  gam_idx, bet_idx = np.where(energy_grid >= energy_grid.max() - atol)
  if plotting:
    gam = gam_idx + .5  # add half a pixel
    bet = bet_idx + .5  
  else: 
    gam = gam_idx + 0.
    bet = bet_idx + 0.
  gam *= gammaMax/energy_grid.shape[0]  # adjust scale
  bet *= betaMax/energy_grid.shape[1]
  
  return gam, bet


def param_transferable(e1, e2, a=.8, b=.7):
  threshold1 = a*e1.max() + (1-a)*e1.min() - 1e-5
  threshold2 = b*e2.max() + (1-b)*e2.min() - 1e-5
  # idx where values are in the top 5%
  e1_max = np.where(e1 >= threshold1)
  if np.count_nonzero(e2[e1_max] >= threshold2) / len(e2[e1_max]) >= .8:
    # if more than 75% align
    print(np.count_nonzero(e2[e1_max] >= threshold2) / len(e2[e1_max]))
    return True
  else:
    return False


def maxcut(G):
  """ 
  Brute force maxcut algorithm.
  Cut has LSB first.
  """
  
  maxcut_val = 0
  for cut in product([0,1], repeat=len(G)):
    cut = np.array(cut)[::-1]
    # only go through half of the cuts
    if cut[-1] == 1: 
      break

    val = cut_value(G, cut)
    if val > maxcut_val:
      maxcut_val = val
      opt_cut = cut
  #opt_cut = ''.join(map(str,opt_cut))
  return opt_cut


def GW_maxcut(G):
  """ 
  GW as done by visually explained 
  https://www.youtube.com/watch?v=aFVnWq3RHYU

  LSB first in returned list
  """
  X = cp.Variable((len(G), len(G)), symmetric=True)

  constraints = [X >> 0]  # positive definite
  constraints += [X[i,i] == 1 for i in range(len(G))]  # unit vectors
  objective = sum(0.5 * (1- X[i,j]) for (i,j) in G.edges())

  prob = cp.Problem(cp.Maximize(objective), constraints)
  prob.solve()

  x = sqrtm(X.value)
  u = np.random.randn(len(G))  # normal to a random hyperplane
  x = np.sign(x @ u)

  # conversion
  x = np.real(x)
  x = (x + 1) / 2

  return x.astype(int)


def transferability_coeff(donor_grid, acceptor_grid):
  """ 
  Take maxima locations of donor, average value in acceptor compared to acceptor maximum.
  """
  if donor_grid.shape != acceptor_grid.shape:
    raise ValueError(f"Energy grids must have the same size, but have sizes {donor_grid.shape} and {acceptor_grid.shape}!")
  idx_locations = np.where(donor_grid >= donor_grid.max() - 1e-5)
  # normalize acceptor to range from [0, 1]
  acceptor = (acceptor_grid - acceptor_grid.min()) / (acceptor_grid.max() - acceptor_grid.min())  
  return np.average(acceptor[idx_locations])

def average_difference(donor_grid, acceptor_grid):
  """ 
  Scale each grid to [0., 1.]; 
  return average difference
  """
  if donor_grid.shape != acceptor_grid.shape:
    raise ValueError(f"Energy grids must have the same size, but have sizes {donor_grid.shape} and {acceptor_grid.shape}!")
  # normalize grids to range from [0, 1]
  donor = (donor_grid - donor_grid.min()) / (donor_grid.max() - donor_grid.min())  
  acceptor = (acceptor_grid - acceptor_grid.min()) / (acceptor_grid.max() - acceptor_grid.min())
  diff = np.abs(donor - acceptor)
  return np.average(diff)

