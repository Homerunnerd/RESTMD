#!/usr/bin/env python2.7

import os,sys
from numpy import *

########### ST-WHAM for python...##########
# Originally written in f90 by Jaegil Kim #
# Translated to Python by David Stelter   #
###########################################
#
# CITE: http://dx.doi.org/10.1063/1.3626150
# Kim, J., Keyes, T., & Straub, J. E. (2011)
#
# WARNING: ONLY for use with RESTMD/STMD!
# http://dx.doi.org/10.1021/jp300366j
# http://dx.doi.org/10.1103/PhysRevLett.97.050601
#
# Requires list enthalpies for each replica
# in separate files AND the latest Ts array
# for use as the sampling weight, oREST
# files will work fine.
#
# Script will automatically read into histograms,
# run through the ST-WHAM machinery and calculate
# Ts(H) and Entropy based on the RESTMD sampling
# weight.
#

## UNITS!!! IMPORTANT!!!
kb = 0.0019872041       #kcal/mol*K
#kb = 0.000086173324    #ev/K
#kb = 0.0083144621      #kj/mol*K
#kb = 1.0               #reduced/LJ


def Falpha(i, j):
# Linear entropy interpolation based on Ts(H)
    Falpha = 0
    for indx in range(i+1,j):
        if (TH[indx] == TH[indx-1]):
            Falpha = Falpha + binsize/TH[indx]
        else:
            Falpha = Falpha + binsize/(TH[indx] - TH[indx-1])*log(TH[indx]/TH[indx-1])
    return Falpha


## Input parameters from inp.stwham
print "ST-WHAM for (RE)STMD\n"
ifile = open('inp.stwham', 'r')
idata = ifile.readlines()
num_lines = len(idata)

if (num_lines > 8 or num_lines < 8):
    print "Err: Invalid input: Incorrect parameters, remove any extra newlines. Should be:\n"
    print "..."
    sys.exit()

## Cast inputs...
binsize = double(idata[0])
Emin = double(idata[1])
Emax = double(idata[2])
T0 = double(idata[3])
T1s = array(map(double, idata[4].split())) # List of Tlo
T2s = array(map(double, idata[5].split())) # List of Thi
rest_num = int(idata[6])
checklimit = double(idata[7]) # Cutoff for contribution from neighbor replicas


## Initialize outputs...
#hout = open('histogram_stwham.dat', 'w')
tout = open('Ts_stwham.dat', 'w')
fracout = open('fract_stwham.dat', 'w')


## Calculate some constants...
nbin = int((Emax-Emin)/binsize) + 2
nReplica = len(T1s)
shape = (nbin, nReplica)
fullshape = (nbin, nReplica+1)


## Final checks...
if (nbin < 0):
    print "Err: Emin must be smaller than Emax.\n"
    sys.exit()
if (nReplica < 1):
    print "Err: Must supply list of T1 and Th for each replica.\n"
    sys.exit()
if (len(T1s) != len(T2s)):
    print "Err: Must have Tlo and Thi for all replicas.\n"
    sys.exit()



## Prepare raw enthalpy files into histograms...
print "Reading in raw data, writting to histograms...\n"
hist = zeros(shape)
edges = zeros(nbin)
print "Replica: "
for l in range(nReplica):
    sys.stdout.write("%d<->%d " % (T1s[l], T2s[l]))
    sys.stdout.flush()
    data = loadtxt("../replica-%d.dat" % l)
    # Calculate histogram
    hist[:,l], edges = histogramdd(ravel(data), bins=nbin, range=[(Emin, Emax)])

    #for i in range(nbin):
        #hout.write("%f %f\n" % (edges[0][i], hist[i][l]))
    #hout.write("%f 0.000000\n" % Emax)
    #hout.write("\n")
print "\n"


## Assign some arrays...
TH = zeros(nbin) # Statistical Temperature
Ent = zeros(nbin) # Entropy
PDF2D_RESTMD = zeros(fullshape) # Enthalpy distribution for all replicas and total data
Y2 = zeros(shape) # Latest sampling weight for all replicas
NumData = zeros(nReplica+1) # Count of data points
betaH = zeros(nbin)
betaW = zeros(nbin)
hfrac = zeros(shape) # Histogram fraction, useful for debugging


## Collect data, and normalize...
for l in range(nReplica):
    Y2[:,l] = genfromtxt("../restart/oREST.%d.d-%d" % (l, rest_num), skip_footer=2, skip_header=13, delimiter=" ")

for l in range(1,nReplica+1):
    count = 0
    for i in range(nbin):
        PDF2D_RESTMD[i][l] = hist[i][l-1] # PDF of each replica
        count = count + PDF2D_RESTMD[i][l]
        PDF2D_RESTMD[i][0] = PDF2D_RESTMD[i][0] + PDF2D_RESTMD[i][l] # PDF of total data set

    PDF2D_RESTMD[:,l] = PDF2D_RESTMD[:,l] / count
    NumData[l] = count # Number of data in each replica
    NumData[0] = NumData[0] + count # Total number of data

PDF2D_RESTMD[:,0] = PDF2D_RESTMD[:,0] / NumData[0] # Normalized PDF


## Throw out edge data under checklimit...
bstart = None
bstop = None
for i in range(nbin):
    if (PDF2D_RESTMD[i][0] > checklimit):
        bstart = i + 3
        break

if (bstart == None):
    print "Err: Energy range not large enough, decrease Emin.\n"
    sys.exit()

for i in range(nbin-1,bstart,-1):
    if (PDF2D_RESTMD[i][0] > checklimit):
        bstop = i - 3
        break

if (bstop == None):
    print "Err: Energy range not large enough, increase Emax.\n"
    sys.exit()


## Calculate Ts(H)
for i in range(bstart,bstop):
    if (PDF2D_RESTMD[i+1][0] > checklimit and PDF2D_RESTMD[i-1][0] > checklimit):
        betaH[i] = (log(PDF2D_RESTMD[i+1][0] / PDF2D_RESTMD[i-1][0])) / (2*binsize / kb) #NOTE: UNITS important here!
    else:
        betaH[i] = 0

    for l in range(1,nReplica+1):
        # Calc B^eff_alpha
        if (PDF2D_RESTMD[i][0] > 0): # ensure positive, no empty bins
            if (Y2[i][l-1] <= 0):
                w = 1 / 0.001
                print "WARNING: Negative Temperature detected...\n"
            else:
                w = 1 / (Y2[i][l-1] * T0)

            betaW[i] = betaW[i] + ((NumData[l] * PDF2D_RESTMD[i][l]) / (NumData[0] * PDF2D_RESTMD[i][0]) * w)
    TH[i] = 1 / (betaH[i] + betaW[i])
    #tout.write("%f %f %f %f\n" % (Emin+(i*binsize), TH[i], betaH[i], betaW[i]))


## Calculate histogram fraction...
for l in range(1,nReplica+1):
    for i in range(bstart,bstop):
        hfrac[i][l-1] = hist[i][l-1] / (PDF2D_RESTMD[i][0] * NumData[0])
        fracout.write("%f %f\n" % (Emin+(i*binsize), hfrac[i][l-1]))
    fracout.write("\n")


## Calculate entropy...
for i in range(bstart,bstop):
    Ent[i] = Falpha(bstart, i)
    tout.write("%f %f %f %f %f\n" % (Emin+(i*binsize), TH[i], Ent[i], betaH[i], betaW[i]))





sys.exit()