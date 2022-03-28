# -*- coding: utf-8 -*-
"""QAOA-parameter-landscape.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1N2gfTEO9N0lGMx9Y9VNKk7UVGKF69r2W
"""


import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.algorithms import QAOA
from qiskit.algorithms.optimizers import COBYLA
from qiskit.opflow import I, X, Y, Z, StateFn, CircuitStateFn, PauliExpectation
from qiskit import Aer, execute, BasicAer

import networkx as nx
from networkx import Graph

import matplotlib.pyplot as plt
import os

# Graph
G = Graph()
G.add_nodes_from(range(6))
G.add_edges_from([(0,1), (1,2), (1,3), (1,4), (2,3), (3,4), (3,5)])
nx.draw(G, with_labels=True)

def operator_from_graph(G: Graph) -> str:
  operator = 0
  for u, v in G.edges():
    s = ['I']*len(G)  # List ['I', 'I', ..], as many Is as nodes
    s[u] = 'Z'
    s[v] = 'Z'
    s = s[::-1]  # reverse, so qbit 0 is node 0
    operator += eval('^'.join(s)) #* G[u][v]['weight']
  return -0.5 * operator

# Value of a given cut
cutValueDict = {}
def cut_value(G: Graph, x: str) -> int:
  #val = cutValueDict.get(x)
  #if val is not None:
  #  return val
  #else:
    result = 0
    x = x[::-1]  # reverse the string since qbit 0 is LSB
    for edge in G.edges():
      u, v = edge
      #weight = G.get_edge_data(u,v, 'weight')['weight']
      if x[u] != x[v]: 
        result += 1 #weight
    #result= -(len(G.edges())/2- result)
    cutValueDict[x] = result
    return result

print(cut_value(G,'00100000'))

optimizer = COBYLA()
qaoa = QAOA(optimizer=optimizer, reps=1, mixer=None, expectation=None)

#operator = 0.5 * ((Z^Z^I) + (I^Z^Z))  # maxcut = 110/001
operator = operator_from_graph(G)
print(operator)

gamma = Parameter(r'$\gamma$')
beta = Parameter(r'$\beta$')
qaoa_qc = qaoa.construct_circuit([beta, gamma], operator)[0]

from qiskit.compiler import transpile
transpile(qaoa_qc, basis_gates=['h', 'rz', 'rx', 'cx']).draw('mpl')
#qaoa_qc.draw('mpl')

# Energies
def get_energy(G, qaoa_qc, gamma, beta, sim=Aer.get_backend('statevector_simulator'), shots=1024):
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
    energy -= cut_value(G, cut) * prob
    # normalize
  if str(sim) != 'statevector_simulator':
    energy = energy / shots

  return energy

#print(get_energy(G, qaoa_qc, gamma=0.2*np.pi, beta=0.3*np.pi))

def get_energy_grid(G, qaoa_qc, gammaMax=2*np.pi, betaMax=np.pi, samples=100):
  """  Calculate the energies for a 2D parameter space.  """
  gammas, betas = np.mgrid[0:gammaMax:gammaMax/samples, 0:betaMax:betaMax/samples]
  result = np.empty((samples,samples))
  cutValueDict ={}

  for i in range(samples):
    for j in range(samples):
      result[i,j] = get_energy(G, qaoa_qc, gammas[i,j], betas[i,j])
  return result

energy_grid = get_energy_grid(G, qaoa_qc, samples=65)
#energy_grid = np.load('./paper-graphs/4-reg/3_energy.npy')

from matplotlib.ticker import FormatStrFormatter

def plot_energy(energy_grid, gammaMax=2*np.pi, betaMax=np.pi, filename=None):
  fig, ax = plt.subplots()
  img = ax.imshow(energy_grid, cmap='inferno', origin='lower', extent=[0, betaMax, 0, gammaMax])
  plt.colorbar(img)

  ax.set_aspect(betaMax/gammaMax)
  ax.set_xlabel(r'$\beta$')
  ax.set_ylabel(r'$\gamma$')
  plt.xticks(np.linspace(0, betaMax, 5))
  plt.yticks(np.linspace(0, gammaMax, 5))
  ax.xaxis.set_major_formatter(FormatStrFormatter('%.3g'))
  ax.yaxis.set_major_formatter(FormatStrFormatter('%.3g'))
  if filename is not None:
    plt.savefig(f'{filename}_energy-landscape.png', dpi=300)
  else:
    plt.show()

plot_energy(energy_grid)


def save_contents(G, qaoa_qc, energy_grid, name, hyperparams=None, folder=None):
  save = input(f'save to /{folder}/{name}? previous data is overwritten! y/n\n')
  if save != 'y':
    return
  #drive_path = '/content/drive/MyDrive/MA/'
  drive_path = './'
  if folder is not None:
    os.makedirs(drive_path + folder, exist_ok=True)
    path = drive_path + f'{folder}/{name}'
  else:
    path = drive_path + name
  nx.write_weighted_edgelist(G, f'{path}.graph')
  nx.draw(G, with_labels=False)
  plt.savefig(f'{path}_graph.png', dpi=150)
  transpile(qaoa_qc, basis_gates=['h', 'rz', 'rx', 'cx']).draw('mpl', filename=f'{path}_qaoa.png')
  np.save(f'{path}_energy.npy', energy_grid)
  plot_energy(energy_grid, filename=path)


""" 3D-Plot """
samples = 65
gammas, betas = np.mgrid[0:2*np.pi:samples*1j, 0:np.pi:samples*1j]
fig, ax = plt.subplots(dpi=150, subplot_kw={"projection": "3d"})
ax.view_init(elev=30, azim=30)
surf = ax.plot_surface(gammas, betas, energy_grid, cmap='inferno',
                       linewidth=0, antialiased=False)
plt.show()

save_contents(G, qaoa_qc, energy_grid, name='3', folder='paper-graphs/4-reg')